from typing import TypedDict, Annotated, List, Optional, Any
import operator
from langgraph.graph import StateGraph, END
from src.agents.navigator import NavigatorAgent
from src.agents.site_analyzer import SiteAnalyzerAgent
from src.agents.searcher import SearcherAgent
from src.agents.extractor import ExtractorAgent
from src.utils.html_pruner import extract_interactive_elements, extract_coupon_elements
from src.utils.cache import get_cached_strategy, save_cached_strategy
import logging
import asyncio

logger = logging.getLogger(__name__)

# --- 1. Define State ---
def append_errors(existing: List[str], new: List[str]) -> List[str]:
    return existing + new if existing else new

class ScraperState(TypedDict):
    brand: str
    domain: str
    headless: bool                       
    run_searcher: bool                   
    navigator: Optional[NavigatorAgent]  
    page: Optional[Any]                  
    current_url: Optional[str]
    html_content: Optional[str]
    site_analysis: Optional[dict]        
    extractor_decision: Optional[dict]      
    extraction_iterations: int              
    clicked_selectors: List[str]            # New: Memory guardrail
    coupon_candidates: Optional[List[dict]] 
    extracted_codes: List[str]              
    errors: Annotated[List[str], append_errors]


# --- 2. Define Nodes ---
async def navigator_node(state: ScraperState):
    """Agent 1: Opens the browser and gets the initial HTML."""
    logger.info(f"--- [Node: Navigator] Opening {state['domain']} ---")
    
    navigator = state.get("navigator")
    if not navigator:
        navigator = NavigatorAgent(headless=state.get("headless", True))
    
    try:
        page = await navigator.navigate(state["domain"])
        if page:
            html = await page.content()
            url = page.url
            return {
                "navigator": navigator,
                "page": page,
                "html_content": html, 
                "current_url": url, 
                "extraction_iterations": 0,
                "clicked_selectors": [],
                "extracted_codes": [],
                "errors": []
            }
        else:
            return {"errors": [f"Failed to navigate to {state['domain']}"]}
    except Exception as e:
        return {"errors": [f"Navigator error: {str(e)}"]}

async def site_analyzer_node(state: ScraperState):
    """Agent 2: Analyzes the page to find the best search strategy."""
    logger.info(f"--- [Node: Site Analyzer] Analyzing {state['domain']} ---")
    
    cached_plan = get_cached_strategy(state['domain'])
    if cached_plan:
        logger.info(f"⚡ FAST PATH: Using cached strategy for {state['domain']} (Valid for 24h)")
        return {"site_analysis": cached_plan}
    
    html = state.get("html_content")
    if not html:
        return {"errors": ["No HTML content available for analysis."]}
        
    pruned_html = extract_interactive_elements(html)
    logger.info(f"Pruned HTML length: {len(pruned_html)} chars")
    
    analyzer = SiteAnalyzerAgent()
    try:
        analysis_result = await analyzer.analyze(
            domain=state["domain"],
            brand=state["brand"],
            pruned_html=pruned_html
        )
        if analysis_result.get("method") != "unsupported":
            save_cached_strategy(state['domain'], analysis_result)
        return {"site_analysis": analysis_result}
    except Exception as e:
        return {"errors": [f"Analyzer error: {str(e)}"]}

async def searcher_node(state: ScraperState):
    """Agent 3: Executes the search plan using Playwright."""
    logger.info(f"--- [Node: Searcher] Searching for '{state['brand']}' on {state['domain']} ---")
    
    plan = state.get("site_analysis")
    page = state.get("page")
    
    if not plan or plan.get("method") == "unsupported":
        return {"errors": ["No valid search strategy available from Agent 2."]}
        
    searcher = SearcherAgent()
    try:
        success = await searcher.execute_search(page, state["brand"], plan)
        if success:
            new_url = page.url
            new_html = await page.content()
            return {"current_url": new_url, "html_content": new_html}
        else:
            return {"errors": ["Searcher failed to execute the plan."]}
    except Exception as e:
        return {"errors": [f"Searcher error: {str(e)}"]}

async def extractor_observe_node(state: ScraperState):
    """Agent 4 (Observe): Looks at the page and decides next step."""
    iters = state.get("extraction_iterations", 0)
    logger.info(f"--- [Node: Extractor Observe] Iteration {iters+1}/3 on {state['current_url']} ---")
    
    page = state.get("page")
    if not page:
        return {
            "errors": ["No page available for extraction."],
            "extractor_decision": {"page_state": "dead_end"}
        }
        
    try:
        html = await page.content()
        pruned_html = extract_coupon_elements(html)
        
        agent = ExtractorAgent()
        clicked = state.get("clicked_selectors", [])
        decision = await agent.analyze(state["brand"], pruned_html, clicked)
        logger.info(f"Agent 4 Decision: {decision.get('page_state')} -> {decision.get('action_selector') or decision.get('extracted_codes')}")
        
        current_codes = state.get("extracted_codes", [])
        new_codes = decision.get("extracted_codes") or []
        
        return {
            "extractor_decision": decision,
            "extraction_iterations": iters + 1,
            "extracted_codes": current_codes + new_codes
        }
    except Exception as e:
        # FATAL ERROR GUARDRAIL: Force the state to dead_end and increment iteration to guarantee the loop breaks
        logger.error(f"Extractor LLM failed to parse. Forcing dead_end to prevent loop: {e}")
        return {
            "errors": [f"Extractor observe error: {str(e)}"],
            "extractor_decision": {"page_state": "dead_end"},
            "extraction_iterations": iters + 1
        }
        
import urllib.parse

async def extractor_action_node(state: ScraperState):
    """Agent 4 (Action): Executes the click decided by Observe node."""
    logger.info(f"--- [Node: Extractor Action] ---")
    
    page = state.get("page")
    original_domain = state.get("domain")
    decision = state.get("extractor_decision", {})
    selector = decision.get("action_selector")
    
    # Store what we clicked in memory so we don't click it again
    current_clicked = state.get("clicked_selectors", [])
    
    if selector:
        logger.info(f"Clicking selector: {selector}")
        try:
            context = page.context
            
            await page.click(selector, force=True)
            await page.wait_for_timeout(3000)
            
            # --- GUARDRAIL 1: TAB MANAGEMENT ---
            # Coupon sites often open the affiliate link in a new tab, but reveal the code on the original tab.
            all_pages = context.pages
            if len(all_pages) > 1:
                logger.info(f"Detected {len(all_pages)} open tabs. Closing affiliate popups...")
                for p in all_pages:
                    if p != page:
                        await p.close()
                await page.bring_to_front()
                await page.wait_for_timeout(1000) # Settle after tab switch
            # -----------------------------------
            
            # --- GUARDRAIL 2: URL REDIRECT DETECTION ---
            # If the current tab redirected to the brand (e.g. nike.com), it's a dead end.
            current_netloc = urllib.parse.urlparse(page.url).netloc
            if original_domain not in current_netloc:
                logger.warning(f"Redirected off-site to {current_netloc}. Ending loop.")
                return {
                    "errors": [f"Redirected off-site to {current_netloc}"],
                    "extractor_decision": {"page_state": "dead_end"},
                    "clicked_selectors": current_clicked + [selector]
                }
            # -------------------------------------------
            
            new_html = await page.content()
            return {
                "html_content": new_html, 
                "current_url": page.url,
                "clicked_selectors": current_clicked + [selector]
            }
        except Exception as e:
            logger.warning(f"Failed to click {selector}: {e}")
            return {
                "errors": [f"Failed to click selector: {e}"],
                "clicked_selectors": current_clicked + [selector] 
            }
    return {}


# --- 3. Build Graph ---
def build_scraper_graph():
    workflow = StateGraph(ScraperState)

    workflow.add_node("navigator", navigator_node)
    workflow.add_node("site_analyzer", site_analyzer_node)
    workflow.add_node("searcher", searcher_node)
    workflow.add_node("extractor_observe", extractor_observe_node)
    workflow.add_node("extractor_action", extractor_action_node)
    
    workflow.set_entry_point("navigator")
    
    def route_after_nav(state: ScraperState):
        if state.get("site_analysis"):
            return "searcher" if state.get("run_searcher") else END
        return "site_analyzer"
        
    def route_after_analyzer(state: ScraperState):
        if state.get("run_searcher"):
            return "searcher"
        return END
        
    def route_after_observe(state: ScraperState):
        decision = state.get("extractor_decision", {})
        page_state = decision.get("page_state")
        iters = state.get("extraction_iterations", 0)
        
        if iters >= 3 or page_state in ["final_code", "dead_end"]:
            return END
        return "extractor_action"
        
    workflow.add_conditional_edges("navigator", route_after_nav, {"searcher": "searcher", "site_analyzer": "site_analyzer", END: END})
    workflow.add_conditional_edges("site_analyzer", route_after_analyzer, {"searcher": "searcher", END: END})
    
    workflow.add_edge("searcher", "extractor_observe")
    
    workflow.add_conditional_edges("extractor_observe", route_after_observe, {"extractor_action": "extractor_action", END: END})
    workflow.add_edge("extractor_action", "extractor_observe")

    return workflow.compile()
