# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Daily Magic Bot is a Python CLI app that generates a daily email report with weather (Beijing/Jinan) and AI-curated science news. It runs via GitHub Actions at 7:32 AM Beijing time.

## Commands

```bash
python main.py --check          # Preflight: validate config, network, API, SMTP
python main.py --email-test     # Send a simple test email (no API tokens consumed)
python main.py --test --no-send # Generate full report HTML → /tmp, don't send
python main.py --test           # Generate full report → /tmp + send email
python main.py                  # Production mode: generate + send (GitHub Actions default)
```

No test suite or linter is configured. Dependencies: `pip install -r requirements.txt`, Python >= 3.10.

## Architecture

**4-stage pipeline** orchestrated by `main.py`:

1. **Weather** ([weather_parser.py](weather_parser.py)) — Scrapes `weather.com.cn` HTML with BeautifulSoup for two cities. Per-city fault isolation: one city failing doesn't block the other. Module-level `requests.Session()` for connection reuse. Falls back to `DEFAULT_WEATHER` dict on parse errors.

2. **News Fetching** ([news_fetcher.py](news_fetcher.py)) — `MultiSourceNewsFetcher` with 13 sources across 4 groups: Nature web, Nature RSS (4 feeds), Science RSS, ScienceDaily RSS (4 feeds), Psychology RSS (3 feeds: PsyPost, Neuroscience News, PNAS). Parallel fetch via `ThreadPoolExecutor(max_workers=8)`, then dedup by URL, then filter to last 1 day. Per-source article parsing (`_parse_nature_article`, `_parse_sciencedaily_article`, `_parse_science_article`) handles site-specific HTML selectors.

3. **AI Processing** ([gemini_processor.py](gemini_processor.py)) — `GeminiProcessor` using `google-genai` SDK with `gemini-3.5-flash` model. **2 AI calls** total:
   - `generate_master_content()` — Selects a random Harry Potter character, generates a Chinese greeting (100-150 chars blending weather + science news), weather advice per city, and news selection/filtering into categories A (astrophysics), B (metacognition/psychology), C (other major discoveries). News filtered by keyword matching against predefined Chinese/English keyword lists, with strict exclusion rules for category C.
   - `process_news_batch()` — Batch translates titles to Chinese and generates inverted-pyramid summaries (100-400 chars, adaptive to input length).
   - Both calls use exponential backoff retry (15s → 30s → 60s) for 503/429 errors. Schema validation with graceful degradation on malformed responses.

4. **Email** ([email_sender.py](email_sender.py)) — `EmailSender` renders email via `string.Template` from [templates/email.html](templates/email.html) + [templates/email.css](templates/email.css). News displayed in 3 category groups (A → B → C). SMTP sends with exponential backoff (5s → 15s → 30s). Supports both STARTTLS (port 587) and SSL (port 465).

**Config** ([config.py](config.py)) — `Config` class reads from `.env` via `python-dotenv`. Exports a singleton `config` instance. Key env vars: `GEMINI_API_KEY`, `SMTP_*`, `RECEIVER_EMAILS` (comma-separated).

## Key design decisions

- **Unified AI request pattern**: The two-call architecture minimizes API latency and cost by batching work that would otherwise require N+1 calls.
- **ScienceDaily/Science RSS**: These sources use the RSS `description` field directly instead of scraping full articles, since their websites block or are unreliable for scraping.
- **Per-source article fetching**: Only Nature articles are scraped for full text; other sources use RSS summaries. A 0.5s delay between Nature fetches prevents rate limiting.
- **Fault tolerance throughout**: Weather parser, news fetcher, AI processor, and email sender all have independent fallback paths — the email always sends even if some components fail.
- **Chinese output**: All AI-generated content (greetings, summaries, advice) is in Chinese, targeting a Chinese-speaking audience.
