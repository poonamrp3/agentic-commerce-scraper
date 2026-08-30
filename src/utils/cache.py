import json
import os
import time
import logging

logger = logging.getLogger(__name__)

CACHE_FILE = "data/strategy_cache.json"
CACHE_EXPIRY_SECONDS = 86400  # 1 day

def get_cached_strategy(domain: str) -> dict:
    """Returns the cached strategy for a domain if it exists and is less than 1 day old."""
    if not os.path.exists(CACHE_FILE):
        return None
        
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
            
        entry = cache.get(domain)
        if not entry:
            return None
            
        # Check if the cache is older than 1 day
        if time.time() - entry["timestamp"] > CACHE_EXPIRY_SECONDS:
            logger.info(f"Cache for {domain} has expired. Needs re-analysis.")
            return None
            
        return entry["strategy"]
    except Exception as e:
        logger.warning(f"Failed to read cache: {e}")
        return None

def save_cached_strategy(domain: str, strategy: dict):
    """Saves the strategy for a domain into the JSON cache with a timestamp."""
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
            
    cache[domain] = {
        "timestamp": time.time(),
        "strategy": strategy
    }
    
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4)
