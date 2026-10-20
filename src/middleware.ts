import { NextResponse, type NextRequest } from 'next/server'
import { createServerClient } from '@supabase/ssr'

/**
 * Authentication boundary for the whole app.
 *
 * Before this existed, every route and page was publicly reachable and all 28
 * API routes used the service-role client, so `?company=<uuid>` was the only
 * thing separating tenants - a presentation filter, not a security boundary.
 *
 * Two deliberate exemptions, both of which authenticate by a different
 * mechanism rather than not at all:
 *   /api/ingest           - agent telemetry, authenticated by x-agent-secret
 *   /api/telemetry/ingest - same
 * Everything else requires a Supabase session. Pages redirect to /login; API
 * routes return 401 JSON, because a redirect to HTML is useless to a fetch().
 */

const AGENT_SECRET_PATHS = ['/api/ingest', '/api/telemetry/ingest']
const PUBLIC_PATHS = ['/login', '/auth/callback']

function isExempt(pathname: string): boolean {
  return (
    AGENT_SECRET_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`)) ||
    PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))
  )
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (isExempt(pathname)) return NextResponse.next()

  // Pass the response through so Supabase can refresh the session cookie.
  let response = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          response = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  // getUser() revalidates against the auth server. getSession() would only
  // decode the cookie, which a client can tamper with.
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    if (pathname.startsWith('/api/')) {
      return Response.json(
        { error: 'Unauthorized', detail: 'authentication required' },
        { status: 401 }
      )
    }
    const loginUrl = request.nextUrl.clone()
    loginUrl.pathname = '/login'
    loginUrl.searchParams.set('next', pathname)
    return NextResponse.redirect(loginUrl)
  }

  return response
}

export const config = {
  // Everything except Next internals and static assets. Matching broadly and
  // exempting explicitly is the safer default: a new route is protected unless
  // someone deliberately exempts it.
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}
