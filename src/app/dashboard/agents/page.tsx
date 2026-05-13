import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/dashboard/StatusBadge'
import { CostLabel } from '@/components/dashboard/CostLabel'
import { EmptyState } from '@/components/dashboard/EmptyState'

export default async function AgentsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; page?: string }>
}) {
  const sp     = await searchParams
  const status = sp.status ?? ''
  const page   = parseInt(sp.page ?? '1', 10)
  const limit  = 50
  const offset = (page - 1) * limit

  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)

  const res           = await apiFetch(`/api/agents?${params}`)
  const agents: any[] = res?.data  ?? []
  const total: number = res?.count ?? 0
  const hasMore       = res?.pagination?.has_more ?? false

  const filterBtn = (label: string, value: string) => {
    const active = status === value
    return (
      <Link
        href={value ? `/dashboard/agents?status=${value}` : '/dashboard/agents'}
        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
          active ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
        }`}
      >
        {label}
      </Link>
    )
  }

  return (
    <div className="p-6 space-y-4 max-w-6xl">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Agents</h1>
        <p className="text-sm text-zinc-500 mt-0.5">{total.toLocaleString()} registered</p>
      </div>

      {/* Status filter */}
      <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1 w-fit">
        {filterBtn('All',      '')}
        {filterBtn('Active',   'active')}
        {filterBtn('Paused',   'paused')}
        {filterBtn('Inactive', 'inactive')}
      </div>

      {/* Table */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
        {agents.length === 0 ? (
          <EmptyState message="No agents registered" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-zinc-500 text-xs">Name</TableHead>
                <TableHead className="text-zinc-500 text-xs">Status</TableHead>
                <TableHead className="text-zinc-500 text-xs">Type</TableHead>
                <TableHead className="text-zinc-500 text-xs">Model</TableHead>
                <TableHead className="text-zinc-500 text-xs">Platform</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Runs</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Tokens In</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Tokens Out</TableHead>
                <TableHead className="text-zinc-500 text-xs text-right">Cost</TableHead>
                <TableHead className="text-zinc-500 text-xs">Last Run</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {agents.map((a: any) => (
                <TableRow key={a.id} className="border-zinc-800 hover:bg-zinc-800/40">
                  <TableCell className="font-medium text-sm">
                    <Link
                      href={`/dashboard/agents/${a.id}`}
                      className="hover:text-blue-400 transition-colors"
                    >
                      {a.name}
                    </Link>
                  </TableCell>
                  <TableCell><StatusBadge status={a.status} /></TableCell>
                  <TableCell className="text-xs text-zinc-400">{a.agent_type ?? '—'}</TableCell>
                  <TableCell className="text-xs text-zinc-400 font-mono">{a.model ?? '—'}</TableCell>
                  <TableCell className="text-xs text-zinc-400">{a.platform ?? '—'}</TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(a.run_count ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(a.total_tokens_in ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-xs text-zinc-400">
                    {(a.total_tokens_out ?? 0).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-sm text-zinc-300">
                    <CostLabel usd={a.total_cost_usd} />
                  </TableCell>
                  <TableCell className="text-xs text-zinc-500">
                    {a.last_event_at
                      ? new Date(a.last_event_at).toLocaleString()
                      : a.last_run_at
                      ? new Date(a.last_run_at).toLocaleString()
                      : '—'}
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
              href={`/dashboard/agents?${new URLSearchParams({ ...(status ? { status } : {}), page: String(page - 1) })}`}
              className="text-zinc-400 hover:text-zinc-200"
            >
              ← Previous
            </Link>
          )}
          <span className="text-zinc-600">Page {page}</span>
          {hasMore && (
            <Link
              href={`/dashboard/agents?${new URLSearchParams({ ...(status ? { status } : {}), page: String(page + 1) })}`}
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
