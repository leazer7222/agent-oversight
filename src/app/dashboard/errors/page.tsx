import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/dashboard/StatusBadge'
import { DurationLabel } from '@/components/dashboard/DurationLabel'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { Badge } from '@/components/ui/badge'

export default async function ErrorsPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; page?: string }>
}) {
  const sp       = await searchParams
  const category = sp.category ?? ''
  const page     = parseInt(sp.page ?? '1', 10)
  const limit    = 50
  const offset   = (page - 1) * limit

  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (category) params.set('category', category)

  const res = await apiFetch(`/api/errors?${params}`)
  const runs: any[]      = res?.data      ?? []
  const total: number    = res?.count     ?? 0
  const breakdown: any[] = res?.breakdown ?? []
  const hasMore          = runs.length === limit

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Failures</h1>
        <p className="text-sm text-zinc-500 mt-0.5">{total.toLocaleString()} failed run{total !== 1 ? 's' : ''}</p>
      </div>

      {/* Category breakdown chips */}
      {breakdown.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <Link
            href="/dashboard/errors"
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              !category
                ? 'bg-zinc-700 border-zinc-600 text-zinc-100'
                : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200'
            }`}
          >
            All
          </Link>
          {breakdown.map((b: any) => (
            <Link
              key={b.category}
              href={`/dashboard/errors?category=${encodeURIComponent(b.category)}`}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                category === b.category
                  ? 'bg-red-950 border-red-800 text-red-300'
                  : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200'
              }`}
            >
              {b.category} <span className="opacity-60">({b.count})</span>
            </Link>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
        {runs.length === 0 ? (
          <EmptyState message={category ? `No failures with category "${category}"` : 'No failures — all clear'} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-zinc-500 text-xs w-28">Run ID</TableHead>
                <TableHead className="text-zinc-500 text-xs">Agent</TableHead>
                <TableHead className="text-zinc-500 text-xs">Category</TableHead>
                <TableHead className="text-zinc-500 text-xs">Error</TableHead>
                <TableHead className="text-zinc-500 text-xs">Started</TableHead>
                <TableHead className="text-zinc-500 text-xs">Duration</TableHead>
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
                  <TableCell className="text-sm">
                    {r.agent_id ? (
                      <Link href={`/dashboard/agents/${r.agent_id}`} className="hover:text-blue-400 transition-colors">
                        {r.agent_name ?? '—'}
                      </Link>
                    ) : (r.agent_name ?? '—')}
                  </TableCell>
                  <TableCell>
                    {r.error_category ? (
                      <Badge variant="outline" className="text-xs text-red-400 border-red-900/50 bg-red-950/20">
                        {r.error_category}
                      </Badge>
                    ) : (
                      <span className="text-xs text-zinc-600">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-red-400 max-w-[240px] truncate">
                    {r.error ? r.error.replace(/^\[[^\]]+\]\s*/, '') : '—'}
                  </TableCell>
                  <TableCell className="text-xs text-zinc-400">
                    {r.started_at ? new Date(r.started_at).toLocaleString() : '—'}
                  </TableCell>
                  <TableCell className="text-sm text-zinc-300">
                    <DurationLabel ms={r.duration_ms} />
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
              href={`/dashboard/errors?${new URLSearchParams({ ...(category ? { category } : {}), page: String(page - 1) })}`}
              className="text-zinc-400 hover:text-zinc-200"
            >
              ← Previous
            </Link>
          )}
          <span className="text-zinc-600">Page {page}</span>
          {hasMore && (
            <Link
              href={`/dashboard/errors?${new URLSearchParams({ ...(category ? { category } : {}), page: String(page + 1) })}`}
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
