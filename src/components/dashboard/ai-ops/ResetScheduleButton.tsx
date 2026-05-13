'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Check, Settings } from 'lucide-react'
import type { Provider } from '@/lib/ai-ops/types'
import { PROVIDER_SHORT } from '@/lib/ai-ops/types'

const DAYS_OF_WEEK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

interface Props {
  provider: Provider
  currentPeriod: 'weekly' | 'monthly' | null
  currentAnchor: number | null
}

export function ResetScheduleButton({ provider, currentPeriod, currentAnchor }: Props) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [period, setPeriod] = useState<'weekly' | 'monthly'>(currentPeriod ?? 'weekly')
  const [anchor, setAnchor] = useState<number>(currentAnchor ?? 1)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const isConfigured = currentPeriod !== null

  function handlePeriodChange(p: 'weekly' | 'monthly') {
    setPeriod(p)
    // Reset anchor to sensible default for the new period
    setAnchor(p === 'weekly' ? 1 : 1)
  }

  async function submit() {
    setSaving(true)
    await fetch('/api/ai-ops/provider-account', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, quota_reset_period: period, quota_reset_anchor: anchor }),
    })
    setSaving(false)
    setSaved(true)
    setOpen(false)
    setTimeout(() => {
      router.refresh()
      setSaved(false)
    }, 800)
  }

  if (saved) {
    return (
      <span className="flex items-center gap-1 text-xs text-emerald-400">
        <Check className="h-3 w-3" /> Saved
      </span>
    )
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <Settings className="h-3 w-3" />
        {isConfigured ? 'Edit reset' : 'Set reset schedule'}
      </button>

      {open && (
        <div className="absolute left-0 top-6 z-10 w-64 rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl p-3 space-y-3">
          <p className="text-xs text-zinc-400">
            When does your {PROVIDER_SHORT[provider]} quota reset?
          </p>

          {/* Period toggle */}
          <div className="flex gap-1 bg-zinc-800 rounded-md p-0.5">
            {(['weekly', 'monthly'] as const).map(p => (
              <button
                key={p}
                onClick={() => handlePeriodChange(p)}
                className={`flex-1 rounded py-1 text-xs font-medium transition-colors ${
                  period === p
                    ? 'bg-zinc-600 text-zinc-100'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>

          {/* Day selector */}
          {period === 'weekly' ? (
            <div className="space-y-1">
              <p className="text-xs text-zinc-600">Which day?</p>
              <div className="flex gap-1 flex-wrap">
                {DAYS_OF_WEEK.map((day, i) => (
                  <button
                    key={i}
                    onClick={() => setAnchor(i)}
                    className={`px-2 py-1 rounded text-xs transition-colors ${
                      anchor === i
                        ? 'bg-zinc-600 text-zinc-100'
                        : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
                    }`}
                  >
                    {day}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-1">
              <p className="text-xs text-zinc-600">Which day of the month?</p>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={anchor}
                  onChange={e => setAnchor(Math.min(31, Math.max(1, Number(e.target.value))))}
                  className="w-16 rounded bg-zinc-800 border border-zinc-700 px-2 py-1 text-xs text-zinc-200 text-center"
                />
                <span className="text-xs text-zinc-500">of each month</span>
              </div>
            </div>
          )}

          <div className="flex gap-2 pt-1">
            <button
              onClick={submit}
              disabled={saving}
              className="flex-1 rounded bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 hover:bg-zinc-600 transition-colors disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              onClick={() => setOpen(false)}
              className="rounded px-2 py-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
