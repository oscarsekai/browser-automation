# browser-automation — X.com Digest Pipeline

An automated pipeline that scrolls X.com via Chrome DevTools Protocol (CDP), collects and ranks posts, and produces a clean Traditional Chinese HTML digest.

A Chinese version of this document is available at [README.zh-TW.md](./README.zh-TW.md).

---

## Features

- **Headless CDP scroll** — drives a real Chrome session over CDP; scrolls the X.com home feed, collecting posts without any API key
- **Smart ranking** — combines follower tier, freshness, keyword relevance, content density, originality, and engagement into a single score; configurable per-weight
- **AI summarisation + classification** — calls the OpenAI Codex API in batches of 10; each post gets a one-sentence Traditional Chinese summary and an auto-assigned category (`ai`, `geopolitics`, `engineering`, `frontend`, `security`, `finance`, `other`)
- **Static HTML output** — generates a self-contained `index.html` with categorised sections, post counts, and direct post links; ready for GitHub Pages or any static host
- **Markdown digest** — also writes `digest.md` alongside `index.html`; token-efficient plain Markdown for AI agents to consume directly (e.g., `GET /digest.md`)
- **Automatic cleanup** — on build runs, deletes raw capture directories and summary archives older than 3 days by default
- **Git sync attempt** — after writing `index.html` and `digest.md`, stages both, commits with a datestamped message (`2026/4/13 summary`), and attempts to push to the configured upstream while printing the actual git result
- **Snapshot replay** — pass a saved HTML file instead of a live CDP session for offline testing

---

## Requirements

| Dependency | Version |
|-----------|---------|
| Python | ≥ 3.11 |
| Google Chrome | any recent stable |
| `websockets` | ≥ 12.0 |
| `openai` | ≥ 1.0 |

```bash
python3 -m pip install -r requirements.txt
```

---

## Project layout

```
browser-automation/
├── src/
│   ├── browser/          # CDP WebSocket driver + scroll logic
│   ├── pipeline/
│   │   ├── filter.py     # noise removal, dedup
│   │   ├── rank.py       # scoring / top-N selection
│   │   └── summarize.py  # OpenAI batch summarisation + AI category
│   ├── scheduler/
│   │   └── run_once.py   # main entry point
│   ├── storage/
│   │   ├── raw_store.py      # write / cleanup raw captures
│   │   └── summary_store.py  # write / cleanup summary archives
│   ├── web/
│   │   └── build_html.py # HTML rendering, section routing
│   ├── config.py         # settings loaded from .env.local
│   └── domain.py         # dataclasses: Post, PostRecord, SummaryBundle
├── data/                 # runtime output (git-ignored)
│   ├── raw/              # per-run raw captures (3-day default retention)
│   └── summaries/        # per-run HTML + JSON archives (3-day default retention)
├── index.html            # latest digest — committed and deployed
├── digest.md             # same digest as plain Markdown — for AI agents
├── .env.local            # local config (copy from .env.local.example)
├── .env.local.example
└── requirements.txt
```

---

## Quick start

### 1. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

If you use a fresh virtual environment, activate it first and then install requirements before running any command:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.local.example .env.local
```

Open `.env.local` and set at minimum:

```env
# OpenAI Codex token (from ~/.hermes/auth.json or your own key)
OPENAI_API_KEY=sk-...

# Summariser backend + model
SUMMARIZE_BACKEND=acp
SUMMARIZE_MODEL=gpt-5.4-mini
SUMMARIZE_REASONING_EFFORT=low

# CDP connection — match the port you use when launching Chrome
CDP_REMOTE_DEBUGGING_PORT=9333
```

See [Configuration reference](#configuration-reference) for all options.

### 3. Launch a dedicated Chrome profile

```bash
mkdir -p "$HOME/your-profile"

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9333 \
  --user-data-dir="$HOME/your-profile"
```

Log into X.com in that window (one-time setup).

### 4. Run the pipeline

If you are using the project virtual environment, activate it before running any pipeline command:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

```bash
python3 -m src.scheduler.run_once
```

The script will:
1. Restart the Chrome tab to avoid stale cache
2. Navigate to `X_HOME_URL`
3. Scroll `SCROLL_COUNT` times (default 80), pausing `SCROLL_PAUSE_SECONDS` between scrolls
4. Collect, filter, rank, and summarise posts
5. Write `index.html` and `digest.md` to the project root
6. On build runs, clean up data older than `RAW_RETENTION_DAYS` days
7. Attempt `git add index.html digest.md && git commit -m "YYYY/M/D summary" && git push`, then print the actual git outcome

### 5. Replay from a saved snapshot (offline / CI)

```bash
python3 -m src.scheduler.run_once --html-source path/to/snapshot.html
```

---

## Configuration reference

All settings live in `.env.local`. Copy `.env.local.example` as a starting point.

| Variable | Default | Description |
|----------|---------|-------------|
| `SUMMARIZE_BACKEND` | `acp` | Summariser transport: `acp`, `codex`, or `openai` |
| `SUMMARIZE_MODEL` | `gpt-5.4-mini` | Default model used by ACP/direct Codex summarisation |
| `SUMMARIZE_REASONING_EFFORT` | `low` | Reasoning level forwarded to Codex summarisation runs |
| `SCROLL_COUNT` | `80` | Number of scroll steps on the feed page |
| `SCROLL_PAUSE_SECONDS` | `1.5` | Seconds to wait between each scroll |
| `SUMMARY_TOP_N` | `50` | Maximum posts passed to the summariser |
| `SUMMARY_SENTENCE_COUNT` | `5` | Target sentence length per summary (unused by current prompt) |
| `RAW_RETENTION_DAYS` | `3` | Days to keep raw captures and summary archives |
| `SOURCE_WEIGHT_A/B/C` | `1.5 / 1.0 / 0.6` | Follower-tier multipliers (high / mid / low) |
| `FRESHNESS_WEIGHT` | `0.20` | Weight for post recency |
| `RELEVANCE_WEIGHT` | `0.20` | Weight for keyword topic match |
| `DENSITY_WEIGHT` | `0.15` | Weight for content length / information density |
| `ORIGINALITY_WEIGHT` | `0.10` | Weight for original vs retweet |
| `ENGAGEMENT_WEIGHT` | `0.05` | Weight for likes + retweets |
| `DUPLICATE_PENALTY` | `0.25` | Score penalty multiplier for near-duplicate posts |
| `FRONTEND_BOOST_WEIGHT` | `0.18` | Extra boost for posts with strong frontend/UI/browser signals |
| `OUTPUT_DIR` | `data/summaries` | Summary archive root |
| `RAW_DIR` | `data/raw` | Raw capture root |
| `X_HOME_URL` | `https://x.com/` | Feed URL to scrape |
| `FOCUS_KEYWORDS` | *(empty)* | Comma-separated keywords that boost relevance score |
| `DELETE_RAW_AFTER_SUMMARY` | `false` | Delete raw run dir immediately after summarising |
| `CDP_REMOTE_DEBUGGING_HOST` | `localhost` | Chrome CDP host |
| `CDP_REMOTE_DEBUGGING_PORT` | `9333` | Chrome CDP port in the provided example config; runtime fallback is unset unless configured |
| `CDP_TARGET_URL` | `about:blank` | Initial target tab URL for CDP attach |

---

## Scheduling (cron)

Each run always collects. The pipeline tracks a counter: the **third run of the day** automatically triggers the build (merge all data → write `index.html` and `digest.md` → attempt git push). No separate flags needed.

```cron
# Run 1 — morning collection
0 10 * * * cd /path/to/browser-automation && python3 -m src.scheduler.run_once >> logs/cron.log 2>&1

# Run 2 — afternoon collection
0 16 * * * cd /path/to/browser-automation && python3 -m src.scheduler.run_once >> logs/cron.log 2>&1

# Run 3 — evening collection + auto build + git sync attempt (digest ready overnight)
0 22 * * * cd /path/to/browser-automation && python3 -m src.scheduler.run_once >> logs/cron.log 2>&1
```

The digest is published at ~22:00 each night and available when you wake up.

To force an immediate build without waiting for the counter:

```bash
source .venv/bin/activate
python3 -m src.scheduler.run_once --force-build
```

To build only from existing raw data without collecting or launching Chrome:

```bash
source .venv/bin/activate
python3 -m src.scheduler.run_once --build-only
```

By default the summariser now uses the ACP Python SDK to spawn a small repo-local Codex bridge agent over stdio. The bridge is not a permanently running daemon: each summarisation call starts it, uses it, and then lets the process exit. It defaults to `gpt-5.4-mini` with `low` reasoning and can be overridden through `.env.local`.

---

## Categories

Posts are classified by the LLM into one of the following categories:

| Category | Section header |
|----------|---------------|
| `ai` | 🤖 AI 模型與工具 |
| `geopolitics` | 🌐 地緣政治 |
| `engineering` | ⚙️ 軟體工程 |
| `frontend` | 🖥️ 前端開發 |
| `security` | 🔐 資安 |
| `finance` | 💰 財經 |
| `other` | 📌 其他 |

If the LLM returns an unrecognised category the post falls back to keyword matching, then `other`.

---

## Notes

- `index.html` is committed to git and served as the public digest page
- `digest.md` is committed alongside `index.html` — AI agents can fetch it directly at `https://your-domain/digest.md` for token-efficient consumption
- `data/` is git-ignored; all runtime artifacts stay local
- Chrome profile persists login sessions between runs; no re-authentication needed after first login
- If CDP is unavailable the pipeline exits early with a clear error — no partial writes
