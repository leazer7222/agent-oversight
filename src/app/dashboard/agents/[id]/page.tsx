import Link from 'next/link'
import { notFound } from 'next/navigation'
import { apiFetch } from '@/lib/api/fetch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/dashboard/StatusBadge'
import { DurationLabel } from '@/components/dashboard/DurationLabel'
import { CostLabel } from '@/components/dashboard/CostLabel'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { ArrowLeft } from 'lucide-react'
import { formatDateTime } from '@/lib/utils'

export default async function AgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const [agentRes, runsRes] = await Promise.all([
    apiFetch(`/api/agents/${id}`),
    apiFetch(`/api/agents/${id}/runs?limit=20`),
  ])

  if (!agentRes?.agent) notFound()

  const agent       = agentRes.agent
  const runs: any[] = runsRes?.data ?? []
  const totalRuns   = runsRes?.count ?? 0

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <Link href="/dashboard" className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300 transition-colors w-fit">
        <ArrowLeft className="h-4 w-4" /> Back to Overview
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">{agent.name}</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            {agent.agent_type ?? '—'} · {agent.model ?? 'no model'} · {agent.platform ?? '—'}
          </p>
        </div>
        <StatusBadge status={agent.status} />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Total Runs',   value: agent.run_count ?? 0 },
          { label: 'Total Cost',   value: <CostLabel usd={agent.total_cost_usd} /> },
          { label: 'Tokens In',    value: (agent.total_tokens_in ?? 0).toLocaleString() },
          { label: 'Tokens Out',   value: (agent.total_tokens_out ?? 0).toLocaleString() },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg bg-zinc-900 border border-zinc-800 p-3">
            <p className="text-xs text-zinc-500 mb-1">{label}</p>
            <p className="text-sm font-medium text-zinc-200">{value}</p>
          </div>
        ))}
      </div>

      {/* Agent metadata */}
      <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-4 space-y-2">
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-3">Identity</h2>
        {[
          { label: 'Agent ID',   value: agent.id },
          { label: 'Type',       value: agent.agent_type },
          { label: 'Model',      value: agent.model },
          { label: 'Platform',   value: agent.platform },
          { label: 'Last Run',   value: formatDateTime(agent.last_event_at) },
          { label: 'Registered', value: formatDateTime(agent.registered_at) },
        ].map(({ label, value }) => (
          <div key={label} className="flex justify-between text-sm">
            <span className="text-zinc-500">{label}</span>
            <span className="text-zinc-300 font-mono text-xs">{value ?? '—'}</span>
          </div>
        ))}
      </div>

      {/* Run history */}
      <div>
        <h2 className="text-sm font-medium text-zinc-300 mb-3">
          Run History ({totalRuns.toLocaleString()})
        </h2>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
          {runs.length === 0 ? <EmptyState message="No runs yet" /> : (
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-zinc-500 text-xs">Run ID</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Status</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Started</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Duration</TableHead>
                  <TableHead className="text-zinc-500 text-xs text-right">Cost</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Error</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r: any) => (
                  <TableRow key={r.id} className="border-zinc-800 hover:bg-zinc-800/40">
                    <TableCell className="font-mono text-xs text-zinc-400">
                      <Link href={`/dashboard/runs/${r.id}`} className="hover:text-blue-400 transition-colors">
                        {r.id.slice(0, 8)}…
                      </Link>
                    </TableCell>
                    <TableCell><StatusBadge status={r.status} /></TableCell>
                    <TableCell className="text-xs text-zinc-400">
                      {formatDateTime(r.started_at)}
                    </TableCell>
                    <TableCell className="text-sm text-zinc-300">
                      <DurationLabel ms={r.duration_ms} />
                    </TableCell>
                    <TableCell className="text-right text-sm text-zinc-300">
                      <CostLabel usd={r.cost_usd} />
                    </TableCell>
                    <TableCell className="text-xs text-red-400 max-w-[200px] truncate">
                      {r.error ? r.error.replace(/^\[[^\]]+\]\s*/, '') : ''}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        {totalRuns > 20 && (
          <Link
            href={`/dashboard/runs?agent=${id}`}
            className="mt-3 inline-block text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            View all {totalRuns} runs →
          </Link>
        )}
      </div>
    </div>
  )
}
