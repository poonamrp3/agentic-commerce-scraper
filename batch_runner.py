import csv
import asyncio
import argparse
from main import run_scraper

async def run_batch(file_path: str, limit: int):
    brands = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'name' in row and row['name'].strip():
                    brands.append(row['name'].strip())
    except Exception as e:
        print(f"Failed to read {file_path}: {e}")
        return

    if not brands:
        print(f"No brands found in {file_path}!")
        return

    # Slice the list if a limit is provided
    if limit and limit > 0:
        brands = brands[:limit]

    print(f"🚀 Starting batch run for {len(brands)} brands...")
    
    for idx, brand in enumerate(brands):
        try:
            # 1. Normalize the brand name via LLM
            from src.utils.brand_normalizer import normalize_brand_name
            clean_brand = await normalize_brand_name(brand)
            
            print(f"\n\n{'#'*80}")
            print(f"### BATCH {idx+1}/{len(brands)}: RUNNING SCRAPER FOR '{clean_brand}' (Original CSV: {brand})")
            print(f"{'#'*80}\n")
            
            # 2. We await the main scraper logic for the cleaned brand
            await run_scraper(clean_brand)
        except Exception as e:
            print(f"❌ Failed to complete scraper for {brand}: {e}")
            
    print(f"\n🎉 Batch run complete! Check the extracted_codes_*.json files for results.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch run the Multi-Agent Coupon Scraper")
    parser.add_argument("--file", type=str, default="data/brand_categorie.csv", help="Path to the brands CSV file")
    parser.add_argument("--limit", type=int, default=3, help="Number of brands to test (default 3). Set to 0 to run all 7,000+ brands.")
    
    args = parser.parse_args()
    
    # Run the async batch loop
    asyncio.run(run_batch(args.file, args.limit))
