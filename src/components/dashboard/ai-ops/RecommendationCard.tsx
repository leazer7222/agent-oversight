'use client'

import { useState } from 'react'
import { ThumbsUp, ThumbsDown, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Recommendation } from '@/lib/ai-ops/types'
import { PROVIDER_SHORT } from '@/lib/ai-ops/types'

interface Props {
  recommendation: Recommendation
  recommendationId: string | null
}

export function RecommendationCard({ recommendation: rec, recommendationId }: Props) {
  const [feedback, setFeedback] = useState<boolean | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const isStale = rec.stale || new Date() > rec.valid_until

  async function submitFeedback(was_accurate: boolean) {
    if (!recommendationId || submitting) return
    setSubmitting(true)
    setFeedback(was_accurate)
    await fetch('/api/ai-ops/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recommendation_id: recommendationId, was_accurate }),
    })
    setSubmitting(false)
  }

  const confidenceColor =
    rec.confidence === 'high'     ? 'text-emerald-400' :
    rec.confidence === 'moderate' ? 'text-yellow-400' :
    'text-zinc-500'

  return (
    <div className={cn(
      'rounded-lg border bg-zinc-900 p-5 space-y-4',
      isStale ? 'border-zinc-700 opacity-70' : 'border-zinc-700'
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Today's Recommendation</p>
          {rec.recommended_provider ? (
            <h2 className="text-lg font-semibold text-zinc-100">{rec.headline}</h2>
          ) : (
            <h2 className="text-base font-medium text-zinc-400">{rec.headline}</h2>
          )}
        </div>
        <span className={cn('text-xs font-medium shrink-0 mt-1', confidenceColor)}>
          {rec.confidence.charAt(0).toUpperCase() + rec.confidence.slice(1)} confidence
        </span>
      </div>

      {/* Stale warning */}
      {isStale && (
        <div className="flex items-center gap-2 text-xs text-yellow-500 bg-yellow-500/10 border border-yellow-500/20 rounded px-3 py-2">
          <RefreshCw className="h-3 w-3" />
          Recommendation is stale — refresh the page to update
        </div>
      )}

      {/* Reasons */}
      {rec.reasons.length > 0 && (
        <ul className="space-y-1">
          {rec.reasons.map((r, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
              <span className="text-zinc-600 mt-0.5">·</span>
              {r}
            </li>
          ))}
        </ul>
      )}

      {/* Secondary */}
      {rec.secondary && (
        <p className="text-xs text-zinc-500">
          Secondary:{' '}
          <span className="text-zinc-400">{PROVIDER_SHORT[rec.secondary.provider]}</span>
          {' '}— {rec.secondary.note}
        </p>
      )}

      {/* Cautions */}
      {rec.cautions.map((c, i) => (
        <p key={i} className="text-xs text-yellow-500/80">⚠ {c}</p>
      ))}

      {/* Feedback */}
      <div className="flex items-center gap-3 pt-1 border-t border-zinc-800">
        <span className="text-xs text-zinc-600">Was this right?</span>
        {feedback === null ? (
          <>
            <button
              onClick={() => submitFeedback(true)}
              disabled={submitting || !recommendationId}
              className="flex items-center gap-1 text-xs text-zinc-500 hover:text-emerald-400 transition-colors disabled:opacity-40"
            >
              <ThumbsUp className="h-3.5 w-3.5" /> Yes
            </button>
            <button
              onClick={() => submitFeedback(false)}
              disabled={submitting || !recommendationId}
              className="flex items-center gap-1 text-xs text-zinc-500 hover:text-red-400 transition-colors disabled:opacity-40"
            >
              <ThumbsDown className="h-3.5 w-3.5" /> No
            </button>
          </>
        ) : (
          <span className="text-xs text-zinc-500">
            {feedback ? '👍 Marked accurate' : '👎 Marked inaccurate'} — thanks
          </span>
        )}
      </div>
    </div>
  )
}
