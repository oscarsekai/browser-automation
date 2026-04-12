
# Source policy

## v1 source strategy
- Start with X.com Home capture.
- Treat raw captures as temporary job artifacts only.
- Keep weights and tuning in `.env.local`.
- Avoid syncing raw content into the main vault or durable knowledge base.

## Retention
- Raw data: short-lived, e.g. 1–3 days, or delete immediately after summary generation if desired.
- Summary data: durable static HTML plus optional JSON metadata.

## Non-goals
- No automatic source discovery.
- No Discord or Obsidian push integration.
- No fancy frontend in v1.
