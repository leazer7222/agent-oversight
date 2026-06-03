# Optimization Agent — Lessons Learned

Format: `[YYYY-MM-DD] | what went wrong | rule going forward`

[2026-03-30] | Default OVERSIGHT_URL included the full /api/ingest path — SDK appends it automatically, causing a double-path 404 | Pass only the base URL to OversightClient (e.g. http://localhost:3000), never the full endpoint path
[2026-03-30] | Unicode arrow character (→) in print statements crashed on Windows cp1252 stdout | Add sys.stdout.reconfigure(encoding="utf-8") at the top of any agent that prints non-ASCII chars
[2026-03-30] | OVERSIGHT_SECRET env var was not set in .env.local (it is named INGEST_SECRET) | Always fall back to INGEST_SECRET when OVERSIGHT_SECRET is missing; add both to the env var lookup
