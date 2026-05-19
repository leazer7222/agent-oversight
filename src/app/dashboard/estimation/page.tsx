import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import { formatDateTime } from '@/lib/utils'
import { formatUsd, formatErrorPct, errorSeverity } from '@/lib/cost-intelligence/estimation-metrics'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AccuracyOverview {
  total_evaluations:        number
  complete_evaluations:     number
  incomplete_evaluations:   number
  provisional_evaluations:  number
  completeness_pct:         number | null
  mape:                     number | null
  median_signed_error_pct:  number | null
  underestimate_count:      number
  overestimate_count:       number
  underestimate_rate_pct:   number | null
  within_p95_band_count:    number
  within_p95_band_pct:      number | null
  severe_miss_count:        number
  unevaluated_estimates:    number
}

interface Miss {
  run_id:                string
  estimated_at:          string
  model:                 string
  provider:              string
  estimation_tier:       string
  confidence:            string
  cost_p50_usd:          number
  cost_p95_usd:          number
  actual_cost_usd:       number
  absolute_error_usd:    number | null
  percentage_error:      number | null
  underestimated:        boolean | null
  telemetry_status:      string
  is_outlier:            boolean
  task_type_code:        string
  task_type_label:       string
  task_complexity_bucket: string
  started_at:            string
}

interface OverviewData {
  overview: AccuracyOverview
  misses:   Miss[]
}

// ---------------------------------------------------------------------------
// Small components
// ---------------------------------------------------------------------------

function Kpi({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-4">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className="text-xl font-semibold text-zinc-100">{value}</p>
      {sub && <p className="text-xs text-zinc-500 mt-0.5">{sub}</p>}
    </div>
  )
}

function SeverityBadge({ pct }: { pct: number | null }) {
  const s = errorSeverity(pct)
  const cls =
    s === 'severe' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
    s === 'warn'   ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20' :
                     'bg-green-500/10 text-green-400 border-green-500/20'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs border font-mono ${cls}`}>
      {formatErrorPct(pct)}
    </span>
  )
}

function DirectionBadge({ underestimated }: { underestimated: boolean | null }) {
  if (underestimated == null) return <span className="text-zinc-600">—</span>
  return underestimated
    ? <span className="text-orange-400 text-xs">↑ under</span>
    : <span className="text-blue-400 text-xs">↓ over</span>
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function EstimationOverviewPage() {
  const data = await apiFetch<OverviewData>('/api/estimation/overview')

  if (!data || (data as any).error) {
    return (
      <div className="p-6">
        <p className="text-sm text-zinc-500">Failed to load estimation data.</p>
      </div>
    )
  }

  const { overview: ov, misses } = data
  const hasData = ov.total_evaluations > 0

  return (
    <div className="p-6 space-y-8 max-w-6xl">

      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Estimation</h1>
        <p className="text-sm text-zinc-500 mt-0.5">
          Pre-run cost estimates vs actuals across all agents
        </p>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        <Kpi
          label="Total Evaluations"
          value={ov.total_evaluations.toLocaleString()}
          sub={`${ov.complete_evaluations} complete`}
        />
        <Kpi
          label="MAPE"
          value={ov.mape != null ? `${ov.mape.toFixed(1)}%` : '—'}
          sub="mean abs % error"
        />
        <Kpi
          label="Median Error"
          value={ov.median_signed_error_pct != null
            ? formatErrorPct(ov.median_signed_error_pct)
            : '—'}
          sub="signed; + = underestimate"
        />
        <Kpi
          label="p95 Containment"
          value={ov.within_p95_band_pct != null ? `${ov.within_p95_band_pct}%` : '—'}
          sub={`${ov.within_p95_band_count} runs within band`}
        />
        <Kpi
          label="Underestimate Rate"
          value={ov.underestimate_rate_pct != null ? `${ov.underestimate_rate_pct}%` : '—'}
          sub={`${ov.underestimate_count} under / ${ov.overestimate_count} over`}
        />
        <Kpi
          label="Severe Misses"
          value={ov.severe_miss_count}
          sub="> 200% error"
        />
        <Kpi
          label="Unevaluated"
          value={ov.unevaluated_estimates}
          sub="estimates pending"
        />
      </div>

      {/* Biggest misses table */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-300 mb-3">
          Biggest Misses
          <span className="ml-2 text-xs font-normal text-zinc-500">
            by absolute dollar error — complete telemetry only
          </span>
        </h2>

        {!hasData || misses.length === 0 ? (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-8 text-center">
            <p className="text-sm text-zinc-500">No evaluated runs yet.</p>
            <p className="text-xs text-zinc-600 mt-1">
              Estimates appear here once runs complete and telemetry is reconciled.
            </p>
          </div>
        ) : (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left px-3 py-2.5 text-zinc-500 font-medium">Run</th>
                  <th className="text-left px-3 py-2.5 text-zinc-500 font-medium">Task</th>
                  <th className="text-left px-3 py-2.5 text-zinc-500 font-medium">Model</th>
                  <th className="text-right px-3 py-2.5 text-zinc-500 font-medium">Estimated p50</th>
                  <th className="text-right px-3 py-2.5 text-zinc-500 font-medium">Actual</th>
                  <th className="text-right px-3 py-2.5 text-zinc-500 font-medium">Abs Error</th>
                  <th className="text-right px-3 py-2.5 text-zinc-500 font-medium">% Error</th>
                  <th className="text-center px-3 py-2.5 text-zinc-500 font-medium">Direction</th>
                  <th className="text-left px-3 py-2.5 text-zinc-500 font-medium">Started</th>
                </tr>
              </thead>
              <tbody>
                {misses.map((m) => (
                  <tr key={m.run_id} className="border-b border-zinc-800/60 hover:bg-zinc-800/30 transition-colors">
                    <td className="px-3 py-2.5">
                      <Link
                        href={`/dashboard/estimation/runs/${m.run_id}`}
                        className="font-mono text-blue-400 hover:text-blue-300 transition-colors"
                      >
                        {m.run_id.slice(0, 8)}…
                      </Link>
                      {m.is_outlier && (
                        <span className="ml-1.5 text-yellow-500" title="Outlier">⚠</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-zinc-300">
                      {m.task_type_label}
                      <span className="ml-1 text-zinc-600">{m.task_complexity_bucket}</span>
                    </td>
                    <td className="px-3 py-2.5 font-mono text-zinc-400">{m.model}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-zinc-400">
                      {formatUsd(m.cost_p50_usd)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-zinc-200">
                      {formatUsd(m.actual_cost_usd)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-zinc-300">
                      {formatUsd(m.absolute_error_usd)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <SeverityBadge pct={m.percentage_error} />
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <DirectionBadge underestimated={m.underestimated} />
                    </td>
                    <td className="px-3 py-2.5 text-zinc-500">
                      {formatDateTime(m.started_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Footer link to run drilldown hint */}
      <p className="text-xs text-zinc-600">
        Click any run ID to see the full estimation breakdown, feature snapshot, and artifact timeline.
      </p>

    </div>
  )
}
