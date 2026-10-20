import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { formatDateTime } from '@/lib/utils'

/**
 * Facility sourcing workspace.
 *
 * Written for Cameron, not for an engineer: no run_id, no agent_id, no table
 * names in the primary view. The operations strip is deliberately plain-language
 * ("Emails sent", "Awaiting your approval") because the person running this
 * workflow should not need to know an agent exists.
 */

const PIPELINE: Array<{ key: string; label: string }> = [
  { key: 'discovered', label: 'Discovered' },
  { key: 'qualified', label: 'Qualified' },
  { key: 'outreach_approved', label: 'Approved' },
  { key: 'contacted', label: 'Contacted' },
  { key: 'responded', label: 'Responded' },
  { key: 'meeting_scheduled', label: 'Meeting set' },
  { key: 'negotiating', label: 'Negotiating' },
  { key: 'secured', label: 'Secured' },
]

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: 'warn' | 'good' }) {
  const colour =
    tone === 'warn' ? 'text-amber-400' : tone === 'good' ? 'text-emerald-400' : 'text-zinc-100'
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${colour}`}>{value}</div>
    </div>
  )
}

export default async function SourcingPage({
  searchParams,
}: {
  searchParams: Promise<{ stage?: string }>
}) {
  const sp = await searchParams
  const stage = sp.stage ?? ''

  const [ops, list] = await Promise.all([
    apiFetch('/api/sourcing/operations'),
    apiFetch(`/api/sourcing/facilities${stage ? `?stage=${encodeURIComponent(stage)}` : ''}`),
  ])

  const summary: Record<string, number> = ops?.summary ?? {}
  const pipeline: Array<{ stage: string; facility_count: number }> = ops?.pipeline ?? []
  const facilities: any[] = list?.facilities ?? []
  const counts = new Map(pipeline.map((p) => [p.stage, Number(p.facility_count)]))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Facility sourcing</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Swimming pool facilities that could host recurring lessons, and where each
          conversation stands.
        </p>
      </div>

      {/* Plain-language operations strip. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Facilities found" value={summary.facilities_discovered ?? 0} />
        <Stat label="Qualified" value={summary.qualified ?? 0} tone="good" />
        <Stat label="Need more info" value={summary.needs_info ?? 0} />
        <Stat label="Awaiting your approval" value={summary.pending_approvals ?? 0} tone="warn" />
        <Stat label="Emails sent" value={summary.emails_sent ?? 0} />
        <Stat label="Meetings scheduled" value={summary.meetings_scheduled ?? 0} tone="good" />
      </div>

      {/* Pipeline board. */}
      <div>
        <h2 className="mb-2 text-sm font-medium text-zinc-300">Pipeline</h2>
        <div className="flex flex-wrap gap-2">
          {PIPELINE.map((s) => {
            const n = counts.get(s.key) ?? 0
            const active = stage === s.key
            return (
              <Link
                key={s.key}
                href={`/dashboard/sourcing${active ? '' : `?stage=${s.key}`}`}
                className={`rounded-md border px-3 py-2 text-xs transition-colors ${
                  active
                    ? 'border-zinc-600 bg-zinc-800 text-zinc-100'
                    : 'border-zinc-800 bg-zinc-900/50 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
                }`}
              >
                <span className="block font-medium">{s.label}</span>
                <span className="mt-0.5 block text-lg font-semibold tabular-nums">{n}</span>
              </Link>
            )
          })}
        </div>
      </div>

      {/* Agent health, shown second because Cameron cares about it less than the
          pipeline but still needs to see when something is stuck. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Jobs queued" value={summary.jobs_queued ?? 0} />
        <Stat label="Jobs running" value={summary.jobs_running ?? 0} />
        <Stat
          label="Jobs failed"
          value={summary.jobs_failed ?? 0}
          tone={(summary.jobs_failed ?? 0) > 0 ? 'warn' : undefined}
        />
        <Stat label="Agent spend (recent)" value={`$${(ops?.recent_spend_usd ?? 0).toFixed(4)}`} />
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-zinc-300">
          {stage ? `Facilities: ${stage.replace(/_/g, ' ')}` : 'All facilities'}
        </h2>

        {facilities.length === 0 ? (
          <EmptyState message="No facilities yet. Run discovery to find pools near Katy - every facility links back to its source." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Facility</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Distance</TableHead>
                <TableHead className="text-right">Score</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Unknowns</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Found</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {facilities.map((f: any) => (
                <TableRow key={f.facility_id}>
                  <TableCell className="font-medium text-zinc-200">
                    {f.website ? (
                      <a href={f.website} target="_blank" rel="noreferrer"
                         className="hover:text-white hover:underline">
                        {f.name}
                      </a>
                    ) : f.name}
                    {f.city && <span className="ml-2 text-xs text-zinc-500">{f.city}</span>}
                  </TableCell>
                  <TableCell className="text-zinc-400">
                    {String(f.facility_type ?? 'unknown').replace(/_/g, ' ')}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-zinc-400">
                    {f.distance_miles != null ? `${Number(f.distance_miles).toFixed(1)} mi` : '-'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-zinc-200">
                    {f.score != null ? Number(f.score).toFixed(0) : '-'}
                  </TableCell>
                  <TableCell className="text-zinc-400">
                    {String(f.qualification_status ?? f.pipeline_stage ?? '-').replace(/_/g, ' ')}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-zinc-500">
                    {f.unknown_count ?? 0}
                  </TableCell>
                  <TableCell>
                    {f.source_url ? (
                      <a href={f.source_url} target="_blank" rel="noreferrer"
                         className="text-xs text-zinc-400 hover:text-white hover:underline">
                        {f.source}
                      </a>
                    ) : <span className="text-xs text-zinc-500">{f.source}</span>}
                  </TableCell>
                  <TableCell className="text-xs text-zinc-500">
                    {f.created_at ? formatDateTime(f.created_at) : '-'}
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
