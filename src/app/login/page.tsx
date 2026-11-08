'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

/**
 * Two ways in, one screen:
 *   - Email + password (the operator mailbox, e.g. partnerships@, has a password
 *     set by the platform admin). Signs in on the spot and goes to `next`.
 *   - Magic link, for anyone without a password: no password to store, rotate
 *     or leak. Leave the password box empty and press "Send sign-in link".
 * Neither path creates an account; membership in a company is granted by the
 * platform admin (public.company_members), so an unknown address still lands
 * on the "not a member" screen after signing in.
 */
export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [state, setState] = useState<'idle' | 'working' | 'sent' | 'error'>('idle')
  const [message, setMessage] = useState('')

  function nextPath() {
    const next = new URLSearchParams(window.location.search).get('next') ?? '/dashboard'
    return next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard'
  }

  async function signInWithPassword(e: React.FormEvent) {
    e.preventDefault()
    setState('working'); setMessage('')
    const supabase = createClient()
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) {
      setState('error')
      setMessage(error.message === 'Invalid login credentials' ? 'Wrong email or password.' : error.message)
      return
    }
    window.location.assign(nextPath())
  }

  async function sendMagicLink() {
    if (!email) { setState('error'); setMessage('Enter your email first.'); return }
    setState('working'); setMessage('')
    const supabase = createClient()
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(nextPath())}` },
    })
    if (error) {
      setState('error')
      setMessage(error.message)
    } else {
      setState('sent')
      setMessage('Check your email for a sign-in link.')
    }
  }

  const busy = state === 'working' || state === 'sent'
  const field = 'w-full rounded border border-white/10 bg-neutral-950 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-white/30 focus:outline-none'

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-950 p-6">
      <div className="w-full max-w-sm rounded-lg border border-white/10 bg-neutral-900 p-6">
        <h1 className="text-lg font-semibold text-white">Agent Oversight</h1>
        <p className="mt-1 text-sm text-white/50">Sign in to continue.</p>

        <form onSubmit={signInWithPassword} className="mt-6 space-y-3">
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className={field}
          />
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className={field}
          />
          <button
            type="submit"
            disabled={busy || !password}
            className="w-full rounded bg-white px-3 py-2 text-sm font-medium text-neutral-950 hover:bg-white/90 disabled:opacity-50"
          >
            {state === 'working' && password ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <div className="mt-4 flex items-center gap-3 text-xs text-white/30">
          <span className="h-px flex-1 bg-white/10" />no password?<span className="h-px flex-1 bg-white/10" />
        </div>
        <button
          type="button"
          onClick={sendMagicLink}
          disabled={busy}
          className="mt-3 w-full rounded border border-white/15 px-3 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:opacity-50"
        >
          {state === 'sent' ? 'Link sent' : 'Send sign-in link to my email'}
        </button>

        {message && (
          <p className={`mt-4 text-sm ${state === 'error' ? 'text-red-400' : 'text-emerald-400'}`}>
            {message}
          </p>
        )}
      </div>
    </main>
  )
}
