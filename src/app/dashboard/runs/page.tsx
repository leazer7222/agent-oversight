import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/dashboard/StatusBadge'
import { DurationLabel } from '@/components/dashboard/DurationLabel'
import { CostLabel } from '@/components/dashboard/CostLabel'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { formatDateTime } from '@/lib/utils'

export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; errors_only?: string; page?: string }>
}) {
  const sp = await searchParams
  const status     = sp.status     ?? ''
  const errorsOnly = sp.errors_only === 'true'
  const page       = parseInt(sp.page ?? '1', 10)
  const limit      = 50
  const offset     = (page - 1) * limit

  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (errorsOnly)       params.set('errors_only', 'true')
  else if (status)      params.set('status', status)

  const res = await apiFetch(`/api/runs?${params}`)
  const runs: any[]  = res?.data ?? []
  const total: number = res?.count ?? 0
  const hasMore       = res?.pagination?.has_more ?? false

  const filterBtn = (label: string, qs: Record<string, string>) => {
    const p = new URLSearchParams(qs)
    const active = JSON.stringify(qs) === JSON.stringify(
      Object.fromEntries(Object.entries({ status, errors_only: errorsOnly ? 'true' : '' }).filter(([, v]) => v))
    )
    return (
      <Link
        href={`/dashboard/runs?${p}`}
        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
          active ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
        }`}
      >
        {label}
      </Link>
    )
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Runs</h1>
          <p className="text-sm text-zinc-500 mt-0.5">{total.toLocaleString()} total</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1 w-fit">
        {filterBtn('All', {})}
        {filterBtn('Started', { status: 'started' })}
        {filterBtn('Completed', { status: 'completed' })}
        {filterBtn('Failed', { errors_only: 'true' })}
      </div>

      {/* Table */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
        {runs.length === 0 ? <EmptyState message="No runs match this filter" /> : (
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-zinc-500 text-xs w-32">Run ID</TableHead>
                <TableHead className="text-zinc-500 text-xs">Agent</TableHead>
                <TableHead className="text-zinc-500 text-xs">Status</TableHead>
                <TableHead className="text-zinc-500 text-xs">Started</TableHead>
                <TableHead className="text-zinc-500 text-xs">Duration</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Tokens In</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Tokens Out</TableHead>
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
                  <TableCell className="text-sm text-zinc-300">
                    <DurationLabel ms={r.duration_ms} />
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">{r.tokens_in ?? '—'}</TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">{r.tokens_out ?? '—'}</TableCell>
                  <TableCell className="text-right text-sm text-zinc-300">
                    <CostLabel usd={r.cost_usd} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Pagination */}
      {(page > 1 || hasMore) && (
        <div className="flex items-center gap-3 text-sm">
          {page > 1 && (
            <Link
              href={`/dashboard/runs?${new URLSearchParams({ ...Object.fromEntries(params), page: String(page - 1) })}`}
              className="text-zinc-400 hover:text-zinc-200"
            >
              ← Previous
            </Link>
          )}
          <span className="text-zinc-600">Page {page}</span>
          {hasMore && (
            <Link
              href={`/dashboard/runs?${new URLSearchParams({ ...Object.fromEntries(params), page: String(page + 1) })}`}
              className="text-zinc-400 hover:text-zinc-200"
            >
              Next →
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
