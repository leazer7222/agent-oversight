import Link from 'next/link'
import { notFound } from 'next/navigation'
import { apiFetch } from '@/lib/api/fetch'
import { StatusBadge } from '@/components/dashboard/StatusBadge'
import { DurationLabel } from '@/components/dashboard/DurationLabel'
import { CostLabel } from '@/components/dashboard/CostLabel'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { Badge } from '@/components/ui/badge'
import { ArrowLeft } from 'lucide-react'

const severityColor: Record<string, string> = {
  error:   'bg-red-500/15 text-red-400 border-red-500/20',
  warning: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/20',
  info:    'bg-zinc-700/50 text-zinc-400 border-zinc-600/20',
}

export default async function RunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const [runRes, eventsRes] = await Promise.all([
    apiFetch(`/api/runs/${id}`),
    apiFetch(`/api/runs/${id}/events`),
  ])

  if (!runRes?.run) notFound()

  const run     = runRes.run
  const agent   = runRes.agent
  const outputs = runRes.outputs ?? []
  const events: any[] = eventsRes?.events ?? []
  const summary = eventsRes?.summary ?? {}

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* Back link */}
      <Link href="/dashboard/runs" className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300 transition-colors w-fit">
        <ArrowLeft className="h-4 w-4" /> Back to Runs
      </Link>

      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-zinc-100 font-mono">{id.slice(0, 8)}…</h1>
          <StatusBadge status={run.status} />
        </div>
        <p className="text-sm text-zinc-500">
          {agent ? (
            <Link href={`/dashboard/agents/${agent.id}`} className="hover:text-zinc-300 transition-colors">
              {agent.name}
            </Link>
          ) : '—'} · {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Duration', value: <DurationLabel ms={run.duration_ms} /> },
          { label: 'Cost', value: <CostLabel usd={run.cost_usd} /> },
          { label: 'Tokens In', value: run.tokens_in ?? '—' },
          { label: 'Tokens Out', value: run.tokens_out ?? '—' },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg bg-zinc-900 border border-zinc-800 p-3">
            <p className="text-xs text-zinc-500 mb-1">{label}</p>
            <p className="text-sm font-medium text-zinc-200">{value}</p>
          </div>
        ))}
      </div>

      {/* Error */}
      {run.error && (
        <div className="rounded-lg bg-red-950/30 border border-red-900/40 p-4">
          <p className="text-xs text-red-400 font-medium mb-1">Error</p>
          <p className="text-sm text-red-300 font-mono whitespace-pre-wrap">{run.error}</p>
        </div>
      )}

      {/* Event timeline */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-zinc-300">Event Trace ({events.length})</h2>
          {summary.total_cost_usd > 0 && (
            <span className="text-xs text-zinc-500">
              Cumulative: <CostLabel usd={summary.total_cost_usd} />
              {' · '}{(summary.total_tokens_in + summary.total_tokens_out).toLocaleString()} tokens
            </span>
          )}
        </div>
        {events.length === 0 ? (
          <EmptyState message="No events recorded for this run" />
        ) : (
          <div className="space-y-1">
            {events.map((e: any, i: number) => (
              <div key={e.id ?? i} className="flex gap-3 rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2.5">
                <div className="w-20 shrink-0 text-right">
                  <span className="text-xs text-zinc-600">
                    {e.occurred_at ? new Date(e.occurred_at).toLocaleTimeString() : '—'}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-medium text-zinc-300">{e.event_type}</span>
                    {e.severity && e.severity !== 'info' && (
                      <Badge variant="outline" className={`text-xs py-0 ${severityColor[e.severity] ?? ''}`}>
                        {e.severity}
                      </Badge>
                    )}
                    {e.duration_ms && (
                      <span className="text-xs text-zinc-600">
                        <DurationLabel ms={e.duration_ms} />
                      </span>
                    )}
                  </div>
                  {e.message && (
                    <p className="text-xs text-zinc-400 truncate">{e.message}</p>
                  )}
                </div>
                {(e.cost_usd || e.tokens_in) && (
                  <div className="shrink-0 text-right text-xs text-zinc-600">
                    {e.tokens_in && <span>{e.tokens_in}↑ </span>}
                    {e.tokens_out && <span>{e.tokens_out}↓ </span>}
                    {e.cost_usd && <CostLabel usd={e.cost_usd} />}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Outputs */}
      {outputs.length > 0 && (
        <div>
          <h2 className="text-sm font-medium text-zinc-300 mb-3">Outputs ({outputs.length})</h2>
          <div className="space-y-2">
            {outputs.map((o: any) => (
              <div key={o.id} className="rounded-lg bg-zinc-900 border border-zinc-800 p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Badge variant="outline" className="text-xs text-zinc-400 border-zinc-700">
                    {o.output_type}
                  </Badge>
                  <span className="text-xs text-zinc-600">
                    {o.created_at ? new Date(o.created_at).toLocaleString() : ''}
                  </span>
                </div>
                <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                  {typeof o.content === 'string' ? o.content : JSON.stringify(o.content, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
