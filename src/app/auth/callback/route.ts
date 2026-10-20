import { NextResponse, type NextRequest } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

/** Exchanges the magic-link code for a session cookie, then returns the user
 *  to wherever they were heading before being bounced to /login. */
export async function GET(request: NextRequest) {
  const url = new URL(request.url)
  const code = url.searchParams.get('code')
  const next = url.searchParams.get('next') ?? '/dashboard'

  if (!code) {
    return NextResponse.redirect(new URL('/login?error=missing_code', url.origin))
  }

  const supabase = await createClient()
  const { error } = await supabase.auth.exchangeCodeForSession(code)
  if (error) {
    return NextResponse.redirect(
      new URL(`/login?error=${encodeURIComponent(error.message)}`, url.origin)
    )
  }

  // Only allow same-origin relative redirects - an open redirect here would be
  // a phishing primitive.
  const safeNext = next.startsWith('/') ? next : '/dashboard'
  return NextResponse.redirect(new URL(safeNext, url.origin))
}
