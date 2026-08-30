# Curatte - Agentic Commerce Scraper

## Setup & Execution (How to Run)
1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
2. **Configure Environment Variables:**
   You MUST set your LLM and Proxy keys before running. Copy the provided `.env.example` file to create your `.env` file:
   ```bash
   cp .env.example .env
   ```
   Open the `.env` file and populate it with:
   - `OPENAI_API_KEY`: Your OpenAI API key (or compatible API key).
   - `OPENAI_MODEL`: The model you wish to use (defaults to `gpt-4o-mini`).
   - `PROXY_URL`: Your residential proxy URL (e.g., BrightData, Oxylabs) to bypass Cloudflare bot walls.
   
   *Note: Secrets should never be committed to code. The repository `.gitignore` ensures `.env` stays secure.*

3. **Run the Scraper:**
   Run the full concurrent pipeline for a specific brand:
   ```bash
   python main.py --brand adidas
   ```
   *(Optional)* If you want to see the detailed agentic decision logs instead of the clean UI, append the verbose flag:
   ```bash
   python main.py --brand adidas --verbose
   ```
   Check the `output/` directory for the extracted `{brand}_offers.json` and performance metrics.

---

## 1. Architecture
> **Note:** Please refer to [architecture_diagram.md](./architecture_diagram.md) in this repository (or the attached image) for a complete visual flowchart of this system's pipeline.

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

## 9. V2 Roadmap & Future Improvements (With more time...)
If given a longer runway, I would evolve this MVP into an enterprise-grade V2 architecture focusing on scale and intelligent routing:
1. **AWS Serverless Deployment:** To process 10,000+ brands rapidly, I would migrate away from local `asyncio` loops toward an Event-Driven Architecture using AWS SQS and AWS Lambda. Each Lambda function would spin up a headless browser, process a small batch of brands concurrently, and die, offering infinite horizontal scalability.
2. **LLM Model Routing:** Rather than running a monolithic model for all steps, I would implement dynamic model routing. Fast, cheap models (like Claude Haiku or Gemini Flash) would be routed to simpler classification tasks (Agent 2), saving the expensive, heavy models (like GPT-4o) purely for complex DOM reasoning (Agent 4).
3. **Frontend UI & TypedDict Refactoring:** Transition the CLI into a visual dashboard (e.g., React/Next.js) showing the agents working in real-time, backed by a cleaner, more strictly typed Pydantic implementation for LangGraph's state management.
4. **Enterprise Residential Proxies:** Connect an enterprise proxy rotator (like BrightData Web Unlocker) to natively handle CAPTCHAs and JS challenges at the network layer, dramatically improving the success rate on highly restrictive domains like `wired.com`.
5. **Multimodal Vision Agents:** HTML pruning occasionally deletes the exact elements containing the codes if class names are obfuscated. Upgrading the Extractor to a Vision model (passing Playwright screenshots instead of HTML) would allow the AI to "read" the code exactly as a human does, completely bypassing anti-scraping DOM obfuscation.
