import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { CostLabel } from '@/components/dashboard/CostLabel'
import { EmptyState } from '@/components/dashboard/EmptyState'

export default async function CostsPage({
  searchParams,
}: {
  searchParams: Promise<{ group_by?: string }>
}) {
  const sp      = await searchParams
  const groupBy = sp.group_by === 'project' ? 'project' : 'agent'

  const res = await apiFetch(`/api/cost?group_by=${groupBy}`)
  const rows: any[]  = res?.data    ?? []
  const overall      = res?.overall  ?? {}

  const tabBtn = (label: string, value: string) => {
    const active = groupBy === value
    return (
      <Link
        href={`/dashboard/costs?group_by=${value}`}
        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
          active ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
        }`}
      >
        {label}
      </Link>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Cost</h1>
        <p className="text-sm text-zinc-500 mt-0.5">Token usage and spend across all agents</p>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Total Cost',   value: <CostLabel usd={overall.total_cost_usd} /> },
          { label: 'Total Runs',   value: (overall.total_runs ?? 0).toLocaleString() },
          { label: 'Tokens In',    value: (overall.total_tokens_in  ?? 0).toLocaleString() },
          { label: 'Tokens Out',   value: (overall.total_tokens_out ?? 0).toLocaleString() },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg bg-zinc-900 border border-zinc-800 p-3">
            <p className="text-xs text-zinc-500 mb-1">{label}</p>
            <p className="text-sm font-medium text-zinc-200">{value}</p>
          </div>
        ))}
      </div>

      {/* Group-by toggle */}
      <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1 w-fit">
        {tabBtn('By Agent',   'agent')}
        {tabBtn('By Project', 'project')}
      </div>

      {/* Table */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
        {rows.length === 0 ? (
          <EmptyState message="No cost data recorded yet" />
        ) : groupBy === 'agent' ? (
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-zinc-500 text-xs">Agent</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Runs</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Tokens In</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Tokens Out</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r: any) => (
                <TableRow key={r.agent_id} className="border-zinc-800 hover:bg-zinc-800/40">
                  <TableCell className="text-sm font-medium">
                    {r.agent_id ? (
                      <Link href={`/dashboard/agents/${r.agent_id}`} className="hover:text-blue-400 transition-colors">
                        {r.agent_name ?? r.agent_id.slice(0, 8) + '…'}
                      </Link>
                    ) : (r.agent_name ?? '—')}
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(r.total_runs ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(r.total_tokens_in ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(r.total_tokens_out ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-sm text-zinc-300">
                    <CostLabel usd={r.total_cost_usd} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-zinc-500 text-xs">Project</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Runs</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Tokens In</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Tokens Out</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r: any) => (
                <TableRow key={r.project_id ?? r.project_name} className="border-zinc-800 hover:bg-zinc-800/40">
                  <TableCell className="text-sm font-medium text-zinc-300">
                    {r.project_name ?? r.project_id ?? '—'}
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(r.total_runs ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(r.total_tokens_in ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(r.total_tokens_out ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-sm text-zinc-300">
                    <CostLabel usd={r.total_cost_usd} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
