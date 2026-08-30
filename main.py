import asyncio
import logging
import argparse
import csv
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from src.graph import build_scraper_graph
from src.utils.cache import get_cached_strategy

# Adjust logging so we don't get spammed by httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

async def process_site_phase1(idx, site, brand, graph, results, semaphore):
    """Processes a single site for Phase 1 (Planning)."""
    # 1. Pre-check cache to avoid opening a browser at all!
    cached_plan = get_cached_strategy(site)
    if cached_plan:
        print(f"\n⚡ [Phase 1] {idx}: {site} -> Strategy loaded instantly from Cache!")
        results[site] = {"status": "success", "analysis": cached_plan}
        return

    # 2. If no cache, acquire a semaphore lock to prevent launching 30+ browsers at once
    async with semaphore:
        print(f"\n▶️ [Phase 1] {idx}: {site} -> Launching browser and analyzing...")
        initial_state = {
            "brand": brand,
            "domain": site,
            "headless": True,
            "run_searcher": False,
            "navigator": None,
            "page": None,
            "current_url": None,
            "html_content": None,
            "site_analysis": None,
            "errors": []
        }
        
        try:
            final_state = await graph.ainvoke(initial_state)
            
            if final_state.get("navigator"):
                await final_state["navigator"].close()
                
            if final_state.get("errors"):
                results[site] = {"status": "error", "errors": final_state['errors']}
                print(f"❌ [Phase 1] {site} Failed: {final_state['errors']}")
            else:
                analysis = final_state.get("site_analysis")
                results[site] = {"status": "success", "analysis": analysis}
                print(f"✅ [Phase 1] {site} Strategy: {analysis.get('method') if analysis else 'None'}")
        except Exception as e:
            results[site] = {"status": "error", "errors": [str(e)]}
            print(f"❌ [Phase 1] {site} Exception: {e}")

async def process_site_phase2(idx, site, brand, saved_plan, graph, final_summary, semaphore):
    """Executes the extraction phase for a site concurrently and headlessly."""
    async with semaphore:
        print(f"\n▶️ [Phase 2: Execution] {idx}: {site} ...")
        
        execution_state = {
            "brand": brand,
            "domain": site,
            "headless": True,        # Production mode: Headless for maximum speed
            "run_searcher": True,
            "site_analysis": saved_plan,
            "navigator": None,
            "page": None,
            "current_url": None,
            "html_content": None,
            "errors": []
        }
        
        try:
            final_state = await graph.ainvoke(execution_state)
            
            if final_state.get("navigator"):
                await final_state["navigator"].close()
                
            codes = final_state.get("extracted_codes", [])
            final_summary[site] = codes
            
            if codes:
                print(f"✅ 🎉 EXTRACTED CODES for {site}: {len(codes)} found!")
            else:
                print(f"⚠️ Reached end for {site}, but no codes extracted.")
                
        except Exception as e:
            final_summary[site] = []
            print(f"❌ Execution Exception on {site}: {e}")

async def run_scraper(brand: str):
    # 1. Read CSV
    sites = []
    try:
        with open("./data/coupons_sites.csv", "r", encoding="utf-8") as f:
            sample = f.read(1024)
            f.seek(0)
            delimiter = '\t' if '\t' in sample else ','
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                if 'domain' in row:
                    sites.append(row['domain'])
    except Exception as e:
        print(f"Failed to read CSV: {e}")
        return

    if not sites:
        print("No sites found in CSV!")
        return
        
    print(f"\n🚀 PHASE 1: Lightning Fast Planning for '{brand.upper()}'")
    print(f"📋 Target sites: {len(sites)} from CSV")
    print("-" * 60)
    
    graph = build_scraper_graph()
    results = {}

    import time
    start_time = time.time()
    
    # PHASE 1: Concurrent Planning
    semaphore = asyncio.Semaphore(10)
    tasks = []
    for idx, site in enumerate(sites):
        tasks.append(process_site_phase1(idx+1, site, brand, graph, results, semaphore))
        
    await asyncio.gather(*tasks)

    # --- REMOVED FILTER: RUN ALL SITES IN PHASE 2 ---
    top_sites = sites
    
    print("\n\n" + "=" * 80)
    print(f"🚀 PHASE 2: Concurrent Execution on ALL {len(top_sites)} Sites")
    print("=" * 80)
    
    final_summary = {}
    phase2_semaphore = asyncio.Semaphore(5)
    phase2_tasks = []
    
    # Run Phase 2 concurrently for all 29 sites!
    for idx, site in enumerate(top_sites):
        # If Phase 1 failed, pass a dummy unsupported plan so it fails gracefully in Phase 2
        site_data = results.get(site, {})
        saved_plan = site_data.get("analysis") if site_data.get("status") == "success" else {"method": "unsupported"}
        phase2_tasks.append(process_site_phase2(idx+1, site, brand, saved_plan, graph, final_summary, phase2_semaphore))
        
    await asyncio.gather(*phase2_tasks)
    
    end_time = time.time()
    duration_minutes = (end_time - start_time) / 60

    # --- METRICS CALCULATIONS ---
    total_sites = len(sites)
    sites_with_codes = sum(1 for codes in final_summary.values() if codes)
    coverage = (sites_with_codes / total_sites) * 100 if total_sites > 0 else 0
    throughput = total_sites / duration_minutes if duration_minutes > 0 else 0
    
    # Rough cost estimations: Proxy ($3/GB), LLM ($0.01 per run)
    estimated_cost = total_sites * 0.015
    projection_10k = (10000 / total_sites) * estimated_cost if total_sites > 0 else 0

    print("\n\n" + "=" * 80)
    print(f"BRAND NAME: {brand.upper()}")
    print("-" * 80)
    
    clean_summary = {}
    total_extracted = 0
    for site in top_sites:
        codes = final_summary.get(site, [])
        if codes:
            # Deduplicate dicts based on code/title
            unique_offers = {f"{c.get('code')}-{c.get('title')}": c for c in codes}.values()
            clean_summary[site] = list(unique_offers)
            total_extracted += len(unique_offers)
            
            # Print the actual alphanumeric codes to the terminal so the user sees them!
            offer_codes = [c.get('code') for c in unique_offers if c.get('code')]
            print(f"{site} - Found {len(unique_offers)} offers: {offer_codes}")
        else:
            clean_summary[site] = []
            print(f"{site} - No codes retrieved")
            
    print("=" * 80)
    print("\n📊 RUN METRICS:")
    print(f"Coverage: {coverage:.1f}% ({sites_with_codes}/{total_sites} sites)")
    print(f"Throughput: {throughput:.1f} rows/minute")
    print(f"Estimated Cost: ${estimated_cost:.3f}")
    print(f"10k Row Projection: ${projection_10k:.2f}")
    print(f"Total Offers Extracted: {total_extracted}")
    
    # --- SAVE TO FILE (MVP OUTPUT) ---
    output_data = {
        "brand": brand,
        "metrics": {
            "coverage_percent": coverage,
            "throughput_rpm": throughput,
            "estimated_cost_usd": estimated_cost,
            "projection_10k_usd": projection_10k
        },
        "offers": clean_summary
    }
    
    import os
    os.makedirs("output", exist_ok=True)
    output_file = f"output/{brand.lower()}_offers.json"
    
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)
        print(f"\n💾 SUCCESS: Results and metrics successfully saved to {output_file}")
    except Exception as e:
        print(f"\n❌ Error saving results to file: {e}")
        
    print("🎉 All Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Coupon Scraper")
    parser.add_argument("--brand", type=str, default="nike", help="The brand to search for coupons (e.g., nike, adidas)")
    parser.add_argument("--verbose", action="store_true", help="Show full detailed developer logs (timestamps, modules)")
    args = parser.parse_args()
    
    # --- BEAUTIFUL UI LOGGING ---
    if args.verbose:
        # Ugly but useful for debugging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        # Clean, beautiful output for the reviewer
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    asyncio.run(run_scraper(args.brand))