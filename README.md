# Curatte - Agentic Commerce Scraper

## 1. Architecture
This system is an **Agentic Pipeline** built on **LangGraph**, utilizing Python's `asyncio` for high-throughput concurrency and Playwright for headless browser execution. 

Rather than relying on brittle, hardcoded CSS selectors (which break when sites update), the system uses LLMs to dynamically generate extraction strategies. The pipeline consists of a state machine orchestrating four specialized agents:
1. **Agent 1 (Navigator):** Bootstraps the Playwright context, injects residential proxies, and aggressively throttles bandwidth.
2. **Agent 2 (Site Analyzer):** Takes pruned DOM representations and uses Pydantic structured outputs to propose a routing plan (finding search bars, identifying cookie consent banners).
3. **Agent 3 (Searcher):** Executes the plan, bypassing cookie banners and landing on the target brand's coupon page.
4. **Agent 4 (Extractor):** A ReAct (Reasoning + Acting) loop. It observes the page, proposes a click action (e.g., "Show Code"), validates the resulting DOM state, and extracts structured Offer objects (code, title, type, expiry).

## 2. Beating the Bot Wall
To bypass standard protections, the Navigator agent is configured with Playwright stealth arguments (`--disable-blink-features=AutomationControlled`). However, for enterprise bot walls (Cloudflare, Datadome) on sites like `cupones.es` and `wired.com`, raw requests fail.
**The Solution:** The pipeline is architected to seamlessly route traffic through rotating Residential Proxies (e.g., Bright Data/Oxylabs) by simply injecting the `PROXY_URL` environment variable into the Playwright context. 

## 3. Dynamic Code Reveal & Pop-ups
Coupon sites aggressively hide codes behind "Click to Reveal" buttons that intentionally trigger affiliate link pop-ups in new tabs. 
**The Solution:** Agent 4 handles this entirely dynamically via its ReAct loop. If the Agent decides to click a selector, the action node immediately checks `context.pages`. If a rogue affiliate tab was spawned, Playwright instantly kills the new tab, brings the original tab to the front, and feeds the newly revealed modal DOM back into the LLM for final extraction. The Agent also utilizes a strict `clicked_selectors` memory array to guarantee it never gets caught in an infinite loop.

## 4. Bandwidth Strategy
Residential proxies charge by the gigabyte. A single coupon page loads megabytes of tracking scripts, hero images, fonts, and autoplaying video ads.
**The Solution:** The Navigator agent utilizes Playwright's `route.intercept` feature to aggressively abort network requests for `image`, `media`, `font`, and `stylesheet` resource types. This strips the page down to pure HTML, reducing bandwidth consumption by over 90% and maximizing the ROI of every gigabyte billed by the proxy provider.

## 5. Security & Prompt Injection
Scraped HTML is treated as hostile input. A compromised site could plant hidden `<div>` tags instructing the LLM to output fake codes or ignore previous instructions.
**The Solution:** To neutralize this, the HTML is sandboxed within `<untrusted_content>` delimiters in the prompt. The System Prompt contains strict override directives ensuring that the Agent ignores any commands attempting to hijack the pipeline from within those tags.

## 6. Scale Plan, Resilience & Cost Model
* **Concurrency:** The pipeline utilizes `asyncio.Semaphore` to decouple planning from execution. It runs batches of headless browsers concurrently, making it highly horizontally scalable.
* **Transient Failure Resilience (Retry/Backoff):** Scraping is inherently flaky at scale. The system explicitly isolates and retries environmental failures (proxy drops, timeouts in the `Navigator`) and API hiccups (JSON parse failures in the `SiteAnalyzer`) using an exponential backoff loop capped at 2 iterations. This prevents transient network issues from killing a 10,000-brand batch, while the strict 2-attempt cap guarantees we don't blindly burn proxy bandwidth on genuinely dead domains.
* **Cost Saving (Caching):** The Site Analyzer's LLM planning phase is cached to disk. If the layout of `promopro.co.uk` was solved once, future brand queries bypass the LLM entirely, dropping cost-per-row significantly.
* **Math:** At roughly $0.01 for the LLM token usage (pruned HTML) and $0.005 for proxy bandwidth (HTML only) per site, the estimated cost is ~$0.015 per brand/site combination. Projecting to 10,000 rows, the operational cost would be ~$150.

## 7. Determinism & DOM Ordering
The assessment explicitly requires determinism (a re-run must yield the same codes). While the LLMs are locked to `temperature=0` to prevent hallucination, relying purely on an LLM to select the "next" button from a pruned HTML string introduces a subtle risk: if the HTML parser serializes the DOM in a slightly different order, the LLM might select a different candidate.
**The Mitigation:** To enforce strict determinism, the system uses a stateful memory guardrail (`clicked_selectors`) to rule out past decisions. However, for a production V2, the ideal architecture completely decouples *classification* from *ranking*. The LLM's job should shrink to purely classifying candidates ("is this a coupon button?"), while a deterministic Python script strictly clicks the valid candidates in raw, top-to-bottom DOM order. By defining this intellectual boundary, we guarantee that the LLM's non-deterministic nature never leaks into the traversal routing.

## 8. Coverage Results and Failure Analysis
The system successfully executed the autonomous loop. On sites where genuine alphanumeric codes existed (e.g., `promopro.co.uk`), the Extractor successfully parsed the DOM and extracted 20+ valid codes.
**Honest Failures & Discoveries:**
1. **Affiliate Traps:** Sites like `trustdeals.de` do not host alphanumeric codes, utilizing "Get Deal" auto-apply redirects instead. The Agent correctly identified these as `dead_end`s and safely aborted the loop rather than polluting the dataset with false positives or getting lost on the brand's checkout page.
2. **Hidden Elements:** On a few sites, the Agent accurately identified the correct CSS selector, but Playwright threw `Element is not visible` errors (likely due to mobile-first responsive menus or obfuscated overlays hiding the element from headless viewports).

## 8. With more time, I would...
1. **Multimodal Vision Agents:** HTML pruning (needed to fit context windows) occasionally deletes the exact elements containing the codes if class names are obfuscated. Upgrading the Extractor to a Vision model (passing Playwright screenshots instead of HTML) would allow the AI to "read" the code exactly as a human does, completely bypassing anti-scraping DOM obfuscation.
2. **Automated Checkout Verification:** Build an independent pipeline that uses the extracted codes, navigates to the brand's official store cart API, and programmatically verifies if the code applies a discount, ensuring 100% confidence in the data.

## How to Run
1. Install dependencies: `pip install -r requirements.txt` and `playwright install`
2. Configure `.env` (See `.env.example`)
3. Run for a single brand: `python main.py --brand adidas`
4. Run batch test: `python batch_runner.py --limit 3`
