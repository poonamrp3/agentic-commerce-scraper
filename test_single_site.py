import asyncio
import json
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(message)s')

# Load proxy from .env
load_dotenv()

from src.graph import build_scraper_graph
from src.utils.cache import get_cached_strategy

async def test_single(domain="cupones.es", brand="adidas"):
    graph = build_scraper_graph()
    
    print(f"\n🚀 TESTING PROXY ON: {domain}")
    print("=" * 60)
    
    # --- PHASE 1: PLANNING ---
    print("▶️ [Phase 1] Checking Strategy...")
    analysis = get_cached_strategy(domain)
    
    if analysis:
        print("⚡ Strategy loaded instantly from Cache!")
    else:
        print("🌐 Launching browser for Planning...")
        plan_state = {
            "brand": brand,
            "domain": domain,
            "headless": True,
            "run_searcher": False,
            "navigator": None,
            "page": None,
            "current_url": None,
            "html_content": None,
            "site_analysis": None,
            "errors": []
        }
        
        final_plan = await graph.ainvoke(plan_state)
        
        if final_plan.get("navigator"):
            await final_plan["navigator"].close()
            
        if final_plan.get("errors"):
            print(f"❌ Phase 1 Failed (Proxy blocked?): {final_plan['errors']}")
            return
            
        analysis = final_plan.get("site_analysis")
        print(f"✅ Strategy generated: {analysis.get('method')}")

    # --- PHASE 2: EXECUTION ---
    print("\n▶️ [Phase 2] Executing Extraction...")
    exec_state = {
        "brand": brand,
        "domain": domain,
        "headless": True,
        "run_searcher": True,
        "site_analysis": analysis,
        "navigator": None,
        "page": None,
        "current_url": None,
        "html_content": None,
        "errors": []
    }
    
    final_exec = await graph.ainvoke(exec_state)
    
    if final_exec.get("navigator"):
        await final_exec["navigator"].close()
        
    codes = final_exec.get("extracted_codes", [])
    print("\n" + "=" * 60)
    if codes:
        print(f"🎉 SUCCESS! Extracted {len(codes)} offers: {codes}")
    else:
        print(f"⚠️ Proxy finished, but no codes were extracted. Check logs for 403s!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_single())
