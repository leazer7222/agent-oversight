/**
 * Server-side fetch helper for internal API calls.
 * Uses NEXT_PUBLIC_SITE_URL in production; falls back to localhost
 * using PORT env var (set in .env.local for dev) or 3000.
 */
import { cookies } from 'next/headers'

const BASE =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, '') ||
  `http://localhost:${process.env.PORT ?? 3000}`

/**
 * Forward the caller's session cookie on the server-to-server hop.
 *
 * Dashboard pages are server components: they call apiFetch, which makes a NEW
 * HTTP request to this same app. That request carries no cookies of its own, so
 * once the API routes started requiring authentication the middleware saw an
 * anonymous request and returned 401 - and because apiFetch returns null on
 * failure, every page would have rendered as a convincing empty state rather
 * than an error.
 *
 * The page itself is already behind the middleware, so the user IS
 * authenticated; forwarding their cookie makes the inner request authenticated
 * too, without widening anyone's access.
 */
async function sessionCookieHeader(): Promise<Record<string, string>> {
  try {
    const store = await cookies()
    const all = store.getAll()
    if (all.length === 0) return {}
    return { cookie: all.map((c) => `${c.name}=${c.value}`).join('; ') }
  } catch {
    // cookies() throws outside a request scope (e.g. build-time prerender).
    // No session to forward is a legitimate state, not an error.
    return {}
  }
}

/**
 * Retry budget for cold starts.
 *
 * On 2026-10-20 the dashboard surfaced `TypeError: fetch failed` from
 * /api/agents. Root cause, confirmed from the project's own edge logs: the
 * Supabase project was waking from Free-tier auto-pause and returned 502/521
 * ("web server is down") for roughly one minute before serving normally.
 *
 * A single attempt turns that transient window into a user-visible failure, and
 * because apiFetch swallows errors and returns null, the page renders as though
 * there were simply no data - which is worse than an error, because it looks
 * like a correct empty state.
 *
 * Two short retries cover a cold start without making a genuinely broken
 * backend slow to report. Only connection-level failures and 5xx are retried:
 * a 401 or 404 is an answer, not an outage, and retrying it just wastes time.
 */
const MAX_ATTEMPTS = 3
const BASE_DELAY_MS = 400

function isRetryable(status?: number): boolean {
  if (status === undefined) return true // network/connection failure
  return status >= 500 && status !== 501
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function apiFetch<T = any>(path: string): Promise<T | null> {
  let lastDetail = 'unknown'
  const headers = await sessionCookieHeader()

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const res = await fetch(`${BASE}${path}`, { cache: 'no-store', headers })
      if (res.ok) return (await res.json()) as T

      lastDetail = `HTTP ${res.status}`
      if (res.status === 401 || res.status === 403) {
        console.error(
          `[apiFetch] ${path} returned ${res.status}. The session cookie was ` +
          `${headers.cookie ? 'forwarded' : 'NOT forwarded'}; an authenticated ` +
          `page should not see this.`
        )
        return null
      }
      if (!isRetryable(res.status) || attempt === MAX_ATTEMPTS) {
        if (isRetryable(res.status)) {
          console.error(`[apiFetch] ${path} failed after ${attempt} attempts: ${lastDetail}`)
        }
        return null
      }
    } catch (err) {
      lastDetail = err instanceof Error ? err.message : String(err)
      if (attempt === MAX_ATTEMPTS) {
        // Log it. A silent null here is indistinguishable from "no data",
        // which is exactly how the cold-start failure went undiagnosed.
        console.error(`[apiFetch] ${path} failed after ${attempt} attempts: ${lastDetail}`)
        return null
      }
    }

    // Exponential backoff: 400ms, then 800ms.
    await sleep(BASE_DELAY_MS * 2 ** (attempt - 1))
  }

  return null
}
