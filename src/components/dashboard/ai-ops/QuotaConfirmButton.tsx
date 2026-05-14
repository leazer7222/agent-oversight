'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Check, ChevronDown } from 'lucide-react'
import type { Provider } from '@/lib/ai-ops/types'
import { PROVIDER_SHORT } from '@/lib/ai-ops/types'

interface Props {
  provider: Provider
}

export function QuotaConfirmButton({ provider }: Props) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [pct, setPct] = useState(50)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function submit() {
    setSaving(true)
    await fetch('/api/ai-ops/quota-snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, quota_remaining_pct: pct, snapshot_source: 'user_confirmed' }),
    })
    setSaving(false)
    setSaved(true)
    setOpen(false)
    // Refresh server data
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
        Confirm quota <ChevronDown className="h-3 w-3" />
      </button>

      {open && (
        <div className="absolute left-0 top-6 z-10 w-56 rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl p-3 space-y-3">
          <p className="text-xs text-zinc-400">
            About how much {PROVIDER_SHORT[provider]} quota remains?
          </p>
          <div className="space-y-1">
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={pct}
              onChange={e => setPct(Number(e.target.value))}
              className="w-full accent-emerald-500"
            />
            <div className="flex justify-between text-xs text-zinc-500">
              <span>0%</span>
              <span className="text-zinc-300 font-medium">~{pct}%</span>
              <span>100%</span>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={submit}
              disabled={saving}
              className="flex-1 rounded bg-zinc-700 px-2 py-1.5 text-xs text-zinc-200 hover:bg-zinc-600 transition-colors disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Confirm'}
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
