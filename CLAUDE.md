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

Tests: `pytest` runs offline unit tests in `tests/` (no network, no API tokens). No linter is configured. Runtime deps: `pip install -r requirements.txt` (single source of truth, read dynamically by `pyproject.toml`); dev/test deps: `requirements-dev.txt`. Python >= 3.10.

## Architecture

**4-stage pipeline** orchestrated by `main.py`:

1. **Weather** ([weather_parser.py](weather_parser.py)) — Scrapes `weather.com.cn` HTML with BeautifulSoup for two cities. Forecast blocks are identified by their `h1` period label (e.g. "11日夜间") and aligned to today's date, because the page layout rotates between day/night blocks over the course of the day; temperature ranges are normalized to min~max. Current temperature is extracted from the embedded `observe24h_data` script variable. Per-city fault isolation: one city failing doesn't block the other. Module-level `requests.Session()` for connection reuse. Falls back to `DEFAULT_WEATHER` dict on parse errors.

2. **News Fetching** ([news_fetcher.py](news_fetcher.py)) — `MultiSourceNewsFetcher` with 13 sources across 4 groups: Nature web, Nature RSS (4 feeds), Science RSS, ScienceDaily RSS (4 feeds), Psychology RSS (3 feeds: PsyPost, Neuroscience News, Medical Xpress). Parallel fetch via `ThreadPoolExecutor(max_workers=8)`, then dedup by URL, then filter to last 1 day. Titles/descriptions are sanitized at the source via `clean_text()`.

3. **AI Processing** — split into three layers:
   - [gemini_processor.py](gemini_processor.py) — orchestration: response validation, field-level fallbacks, and `process_daily_report()` entry point. **2 AI calls** total.
   - [prompts.py](prompts.py) — prompt construction (`build_master_prompt`, `build_batch_prompt`) and input formatting (full weather fields incl. current temp/sunrise/sunset/alerts, 100-char truncated news descriptions).
   - [ai_client.py](ai_client.py) — transport: `AiClient.call()` → `_call_gemini_chain` (gemini-3.7-flash → 3.5-flash → 2.5-pro, 2 attempts per model, 30s backoff) → if all Gemini models fail, falls back to `_call_deepseek` (deepseek-v4-flash via OpenAI-compatible `/chat/completions`, backoff 15s/30s × 3). Also hosts `parse_ai_json()` (tolerates Markdown fences, // comments, trailing commas; logs raw text on failure). Records `last_used_model` for the model tag shown at the top of each email.
   - `generate_master_content()` — Selects a random Harry Potter character, generates a Chinese greeting (100-150 chars blending weather + science news), weather advice per city, and news selection/filtering into categories A (astrophysics), B (metacognition/psychology), C (other major discoveries).
   - `process_news_batch()` — Batch translates titles to Chinese and generates inverted-pyramid summaries (100-400 chars, adaptive to input length).
   - Selected articles' full text is fetched concurrently by [async_news_fetcher.py](async_news_fetcher.py) (aiohttp + Semaphore(10)) between the two calls.

4. **Email** ([email_sender.py](email_sender.py)) — `EmailSender` renders email via **Jinja2** (autoescape on): [templates/email.html](templates/email.html) extends [templates/email_base.html](templates/email_base.html) and includes [templates/weather_card.html](templates/weather_card.html) + [templates/news_section.html](templates/news_section.html); [templates/email.css](templates/email.css) is inlined into `<style>`. News displayed in 3 category groups (A → B → C). SMTP sends with exponential backoff (5s → 15s → 30s). Supports both STARTTLS (port 587) and SSL (port 465).

**Config** ([config.py](config.py)) — `Config` class reads from `.env` via `python-dotenv`. Exports a singleton `config` instance. Key env vars: `GEMINI_API_KEY`, `DEEPSEEK_API_KEY` (optional fallback, placeholder disables it), `SMTP_*`, `RECEIVER_EMAILS` (comma-separated).

## Key design decisions

- **Unified AI request pattern**: The two-call architecture minimizes API latency and cost by batching work that would otherwise require N+1 calls.
- **ScienceDaily/Science RSS**: These sources use the RSS `description` field directly instead of scraping full articles, since their websites block or are unreliable for scraping.
- **Per-source article fetching**: Selected articles' full text is fetched concurrently by [async_news_fetcher.py](async_news_fetcher.py) (aiohttp + `Semaphore(10)`); ScienceDaily/Science sources reuse RSS summaries instead of scraping. Fetch failures degrade to the RSS description.
- **Fault tolerance throughout**: Weather parser, news fetcher, AI processor, and email sender all have independent fallback paths — the email always sends even if some components fail.
- **Unified retry**: [retry.py](retry.py) provides `retry_with_backoff()` + `RetryableError` shared by the Gemini chain, DeepSeek fallback, and SMTP sending.
- **Chinese output**: All AI-generated content (greetings, summaries, advice) is in Chinese, targeting a Chinese-speaking audience.
