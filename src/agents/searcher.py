import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)

class SearcherAgent:
    """
    Agent 3: Searcher
    Job: Takes the plan from Agent 2 and actually physically drives the browser to the brand's page.
    """
    async def execute_search(self, page: Page, brand: str, plan: dict) -> bool:
        method = plan.get('method')
        logger.info(f"Executing strategy '{method}' for brand '{brand}'")
        
        # --- NEW: Handle Cookie Banners ---
        cookie_sel = plan.get('cookie_accept_selector')
        if cookie_sel:
            logger.info(f"Cookie banner detected by Agent 2. Clicking accept button: {cookie_sel}")
            try:
                # Use a short timeout so we don't hang if it's already gone
                await page.wait_for_selector(cookie_sel, state="visible", timeout=3000)
                await page.click(cookie_sel, force=True)
                
                # Wait for the animation to slide away
                await page.wait_for_timeout(1500) 
            except Exception as e:
                logger.warning(f"Could not click cookie banner (might not be visible): {e}")
        # ----------------------------------
        
        if method == 'search_bar':
            input_sel = plan.get('search_input_selector')
            btn_sel = plan.get('search_button_selector')
            
            if not input_sel:
                raise ValueError("Agent 2 failed to provide an input selector.")
                
            logger.info(f"Typing '{brand}' into {input_sel}")
            # Ensure the input is visible and fill it
            await page.wait_for_selector(input_sel, state="visible", timeout=5000)
            
            # Dramatic pause for visual testing
            await page.wait_for_timeout(1500) 
            
            await page.fill(input_sel, brand)
            
            # Brief pause to let the user see what was typed and let autocomplete dropdowns trigger
            await page.wait_for_timeout(2000)
            
            if btn_sel:
                logger.info(f"Clicking search button: {btn_sel}")
                # Sometimes buttons are hidden or covered, we force the click
                await page.click(btn_sel, force=True)
            else:
                logger.info("No button selector provided. Pressing Enter.")
                await page.press(input_sel, "Enter")
                
            logger.info("Waiting for the brand's coupon page to load...")
            # Wait for network idle to ensure the new page (or AJAX results) are fully loaded
            await page.wait_for_load_state("networkidle", timeout=15000)
            # Extra buffer just in case
            await page.wait_for_timeout(2000) 
            
            return True
            
        else:
            logger.error(f"Cannot execute unsupported method: {method}")
            return False
