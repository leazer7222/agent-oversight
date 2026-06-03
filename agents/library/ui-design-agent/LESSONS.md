# UI Design Agent — Lessons Learned

Format: `[YYYY-MM-DD] | what went wrong | rule going forward`

[2026-03-30] | Agent lacked OversightClient — run events were never emitted to the oversight system | Always import and use OversightClient in run() so every invocation is tracked
[2026-03-30] | lucide-react missing from project dependencies caused build errors on generated components | Always verify lucide-react is in package.json before delivering UI output to a project
