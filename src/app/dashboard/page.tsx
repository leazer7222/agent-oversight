import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/dashboard/StatusBadge'
import { CostLabel } from '@/components/dashboard/CostLabel'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { ProviderQuotaStrip } from '@/components/dashboard/ProviderQuotaStrip'
import { assembleSignals } from '@/lib/ai-ops/signals'
import { Bot, Play, DollarSign, AlertCircle } from 'lucide-react'
import { formatDateTime } from '@/lib/utils'

export default async function OverviewPage() {
  const [agentsRes, runsRes, costRes, errorsRes, signals] = await Promise.all([
    apiFetch('/api/agents?limit=50'),
    apiFetch('/api/runs?limit=5'),
    apiFetch('/api/cost'),
    apiFetch('/api/errors?limit=5'),
    assembleSignals().catch(() => []),
  ])

  const agents: any[]  = agentsRes?.data  ?? []
  const runs: any[]    = runsRes?.data    ?? []
  const overall        = costRes?.overall  ?? {}
  const errors: any[]  = errorsRes?.data  ?? []
  const totalAgents    = agentsRes?.count  ?? 0
  const totalRuns      = runsRes?.count    ?? 0
  const totalErrors    = errorsRes?.count  ?? 0

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Overview</h1>
        <p className="text-sm text-zinc-500 mt-0.5">Control plane status across all agents</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard icon={Bot} label="Agents" value={totalAgents} />
        <KpiCard icon={Play} label="Total Runs" value={totalRuns} />
        <KpiCard
          icon={DollarSign}
          label="Total Cost"
          value={overall.total_cost_usd != null ? `$${Number(overall.total_cost_usd).toFixed(4)}` : '—'}
        />
        <KpiCard icon={AlertCircle} label="Failed Runs" value={totalErrors} highlight={totalErrors > 0} />
      </div>

      {/* Provider quota strip */}
      {signals.length > 0 && <ProviderQuotaStrip signals={signals} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Agents table */}
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-zinc-300">Agents</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {agents.length === 0 ? <EmptyState message="No agents registered" /> : (
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-zinc-500 text-xs">Name</TableHead>
                    <TableHead className="text-zinc-500 text-xs">Status</TableHead>
                    <TableHead className="text-zinc-500 text-xs text-right">Runs</TableHead>
                    <TableHead className="text-zinc-500 text-xs text-right">Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {agents.slice(0, 8).map((a: any) => (
                    <TableRow key={a.id} className="border-zinc-800 hover:bg-zinc-800/40">
                      <TableCell className="font-medium text-sm">
                        <Link href={`/dashboard/agents/${a.id}`} className="hover:text-blue-400 transition-colors">
                          {a.name}
                        </Link>
                      </TableCell>
                      <TableCell><StatusBadge status={a.status} /></TableCell>
                      <TableCell className="text-right text-zinc-400 text-sm">{a.run_count ?? 0}</TableCell>
                      <TableCell className="text-right text-zinc-400 text-sm">
                        <CostLabel usd={a.total_cost_usd} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Recent errors */}
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium text-zinc-300">Recent Failures</CardTitle>
            <Link href="/dashboard/errors" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
              View all →
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {errors.length === 0 ? <EmptyState message="No failures — all clear" /> : (
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-zinc-500 text-xs">Agent</TableHead>
                    <TableHead className="text-zinc-500 text-xs">Category</TableHead>
                    <TableHead className="text-zinc-500 text-xs">Error</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {errors.map((e: any) => (
                    <TableRow key={e.id} className="border-zinc-800 hover:bg-zinc-800/40">
                      <TableCell className="text-sm">
                        <Link href={`/dashboard/runs/${e.id}`} className="hover:text-blue-400 transition-colors">
                          {e.agent_name ?? 'Unknown'}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs text-zinc-400">{e.error_category ?? '—'}</TableCell>
                      <TableCell className="text-xs text-red-400 max-w-[180px] truncate">
                        {e.error ? e.error.replace(/^\[[^\]]+\]\s*/, '') : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent runs */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium text-zinc-300">Recent Runs</CardTitle>
          <Link href="/dashboard/runs" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
            View all →
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          {runs.length === 0 ? <EmptyState message="No runs yet" /> : (
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="text-zinc-500 text-xs">Run ID</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Agent</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Status</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Started</TableHead>
                  <TableHead className="text-zinc-500 text-xs text-right">Cost</TableHead>
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
                    <TableCell className="text-sm">{r.agent_name ?? '—'}</TableCell>
                    <TableCell><StatusBadge status={r.status} /></TableCell>
                    <TableCell className="text-xs text-zinc-400">
                      {formatDateTime(r.started_at)}
                    </TableCell>
                    <TableCell className="text-right text-sm text-zinc-400">
                      <CostLabel usd={r.cost_usd} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function KpiCard({
  icon: Icon, label, value, highlight = false,
}: {
  icon: any; label: string; value: string | number; highlight?: boolean
}) {
  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">{label}</span>
          <Icon className={`h-4 w-4 ${highlight ? 'text-red-400' : 'text-zinc-600'}`} />
        </div>
        <p className={`text-2xl font-semibold ${highlight && value !== 0 ? 'text-red-400' : 'text-zinc-100'}`}>
          {value}
        </p>
      </CardContent>
    </Card>
  )
}
