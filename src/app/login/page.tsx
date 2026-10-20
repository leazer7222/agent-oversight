'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

/**
 * Magic-link sign-in. Chosen over password auth deliberately: there is no
 * password to store, rotate or leak, and Cameron needs one working path rather
 * than an account-management surface.
 */
export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [message, setMessage] = useState('')

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setState('sending')
    const supabase = createClient()
    const next = new URLSearchParams(window.location.search).get('next') ?? '/dashboard'
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}` },
    })
    if (error) {
      setState('error')
      setMessage(error.message)
    } else {
      setState('sent')
      setMessage('Check your email for a sign-in link.')
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-950 p-6">
      <div className="w-full max-w-sm rounded-lg border border-white/10 bg-neutral-900 p-6">
        <h1 className="text-lg font-semibold text-white">Agent Oversight</h1>
        <p className="mt-1 text-sm text-white/50">Sign in to continue.</p>

        <form onSubmit={onSubmit} className="mt-6 space-y-3">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded border border-white/10 bg-neutral-950 px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-white/30 focus:outline-none"
          />
          <button
            type="submit"
            disabled={state === 'sending' || state === 'sent'}
            className="w-full rounded bg-white px-3 py-2 text-sm font-medium text-neutral-950 hover:bg-white/90 disabled:opacity-50"
          >
            {state === 'sending' ? 'Sending...' : state === 'sent' ? 'Link sent' : 'Send sign-in link'}
          </button>
        </form>

        {message && (
          <p className={`mt-4 text-sm ${state === 'error' ? 'text-red-400' : 'text-emerald-400'}`}>
            {message}
          </p>
        )}
      </div>
    </main>
  )
}
