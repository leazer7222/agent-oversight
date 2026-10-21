import { NextResponse, type NextRequest } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

type OtpType = 'magiclink' | 'email' | 'recovery' | 'invite' | 'signup' | 'email_change'
const OTP_TYPES: OtpType[] = ['magiclink', 'email', 'recovery', 'invite', 'signup', 'email_change']

/**
 * Completes a sign-in and returns the user to wherever they were heading before
 * being bounced to /login. Two documented Supabase link shapes are accepted:
 *
 *   ?code=...                      PKCE flow - the link the login page requests
 *   ?token_hash=...&type=magiclink token-hash flow - the same single-use token
 *                                  the emailed link carries, delivered without
 *                                  SMTP (scripts/dev_signin_link.py uses the
 *                                  Auth admin API to mint one when the email
 *                                  rate limit is hit). Same expiry, same
 *                                  one-time use, same account - no weaker.
 *
 * Nothing here creates a session without a valid Supabase-issued token.
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url)
  const code = url.searchParams.get('code')
  const tokenHash = url.searchParams.get('token_hash')
  const type = url.searchParams.get('type') as OtpType | null
  const next = url.searchParams.get('next') ?? '/dashboard'

  if (!code && !(tokenHash && type && OTP_TYPES.includes(type))) {
    return NextResponse.redirect(new URL('/login?error=missing_code', url.origin))
  }

  const supabase = await createClient()
  const { error } = code
    ? await supabase.auth.exchangeCodeForSession(code)
    : await supabase.auth.verifyOtp({ type: type as OtpType, token_hash: tokenHash as string })
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
