# Marketing Agent — Lessons Learned

Format: `[YYYY-MM-DD] | what went wrong | rule going forward`

[2026-03-30] | Agent lacked OversightClient — run events were never emitted to the oversight system | Always import and use OversightClient in run() so every invocation is tracked
[2026-03-30] | Hardcoded marketing context was used for seller_test run instead of real GDrive data | Context Agent must always be called first; never mock or hardcode context in production runs
