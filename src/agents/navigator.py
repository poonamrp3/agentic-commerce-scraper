import os
import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext, Browser

logger = logging.getLogger(__name__)

class NavigatorAgent:
    """
    Agent 1: Navigator
    Job: Open the coupon site in a headless browser, route through proxies, block unnecessary resources (bandwidth), and return a live page.
    """
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    async def start(self):
        logger.info("Starting Playwright and launching browser...")
        self.playwright = await async_playwright().start()
        
        # --- RESIDENTIAL PROXY CONFIGURATION ---
        proxy_url = os.getenv("PROXY_URL") # e.g. http://username:password@pr.oxylabs.io:7777
        proxy_config = {"server": proxy_url} if proxy_url else None
        
        if proxy_config:
            logger.info("Routing traffic through Residential Proxy...")
            
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            proxy=proxy_config,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars"
            ]
        )
        
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1,
            ignore_https_errors=True # Required for some proxy connections
        )
        
        # --- BANDWIDTH OPTIMIZATION ---
        # Proxies bill by the GB. Block images, videos, and fonts.
        # Note: We are letting 'stylesheet' load so you can visually see the page properly.
        await self.context.route("**/*", self._route_interceptor)

    async def _route_interceptor(self, route):
        """Blocks images, fonts, and media files to save proxy bandwidth."""
        if route.request.resource_type in ["image", "media", "font", "other"]:
            await route.abort()
        else:
            await route.continue_()

    async def navigate(self, domain: str, max_retries: int = 2) -> Optional[Page]:
        """Navigate to a site and return the live Page object, with retry and backoff."""
        if not self.context:
            await self.start()
            
        url = domain if domain.startswith("http") else f"https://{domain}"
        
        for attempt in range(max_retries):
            logger.info(f"Navigating to {url} (Attempt {attempt + 1}/{max_retries})...")
            
            page = await self.context.new_page()
            try:
                # Changed to networkidle so JS-rendered search bars appear
                await page.goto(url, timeout=45000, wait_until="networkidle")
                # Extra buffer for aggressive lazy-loading
                await page.wait_for_timeout(2000) 
                logger.info(f"Successfully loaded {url}")
                return page
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to navigate to {url}: {e}")
                await page.close()
                
                if attempt < max_retries - 1:
                    backoff = 2 ** attempt  # 1s, 2s backoff
                    logger.info(f"Retrying {url} in {backoff} seconds...")
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Max retries exhausted for {url}. Moving on.")
                    return None

    async def close(self):
        """Clean up resources."""
        logger.info("Closing browser resources...")
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
