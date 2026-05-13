/**
 * Server-side fetch helper for internal Read API calls.
 * Uses NEXT_PUBLIC_SITE_URL in production; falls back to localhost.
 */
const BASE =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, '') ||
  'http://localhost:3000'

export async function apiFetch<T = any>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { cache: 'no-store' })
    if (!res.ok) return null
    return res.json() as Promise<T>
  } catch {
    return null
  }
}
