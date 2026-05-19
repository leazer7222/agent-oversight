import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { apiFetch } from '@/lib/api/fetch'
import { formatDateTime } from '@/lib/utils'
import {
  formatErrorPct,
  formatUsd,
  formatTokens,
  errorSeverity,
  FAILURE_MODE_LABELS,
  type EstimateArtifact,
  type EvaluationArtifact,
  type EstimationFailureMode,
} from '@/lib/cost-intelligence/estimation-metrics'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EstimationRunDetail {
  run: {
    id:                      string
    agent_id:                string
    status:                  string
    started_at:              string
    completed_at:            string | null
    cost_usd:                number | null
    tokens_in:               number | null
    tokens_out:              number | null
    error:                   string | null
    task_complexity_bucket:  string
    task_classifier_version: string
  }
  estimate:        EstimateArtifact        | null
  evaluation:      EvaluationArtifact      | null
  recommendation:  Record<string, unknown> | null
  reservation:     Record<string, unknown> | null
  settlement:      Record<string, unknown> | null
  pricing_version: { id: string; version: string; status: string; effective_from: string } | null
  task_type:       { code: string; label: string; min_calibration_runs: number } | null
  events:          Array<{
    id:          string
    event_type:  string
    occurred_at: string
    message:     string | null
    severity:    string
    duration_ms: number | null
    tokens_in:   number | null
    tokens_out:  number | null
    cost_usd:    number | null
  }>
  derived: {
    failureMode:      EstimationFailureMode
    signedErrorUsd:   number
    withinP95Band:    boolean
    tokenInErrorPct:  number | null
    tokenOutErrorPct: number | null
    replayable:       boolean
    explanation:      string[]
  } | null
  error?: string
}

// ---------------------------------------------------------------------------
// Small display components — server-side only, no state
// ---------------------------------------------------------------------------

function Stat({ label, value, mono = false, dim = false }: {
  label: string
  value: React.ReactNode
  mono?:  boolean
  dim?:   boolean
}) {
  return (
    <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-3">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className={`text-sm font-medium ${dim ? 'text-zinc-500' : 'text-zinc-200'} ${mono ? 'font-mono' : ''}`}>
        {value}
      </p>
    </div>
  )
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">{children}</h2>
  )
}

function ArtifactBadge({ label, id, tier }: { label: string; id: string | undefined; tier?: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-zinc-600 bg-zinc-800 rounded px-1.5 py-0.5">{label}</span>
      {id && <span className="text-xs font-mono text-zinc-500">{id.slice(0, 8)}…</span>}
      {tier && <span className="text-xs text-zinc-600">{tier}</span>}
    </div>
  )
}

const SEVERITY_COLORS = {
  ok:     'text-emerald-400',
  warn:   'text-amber-400',
  severe: 'text-red-400',
}

const ERROR_DIRECTION_COLORS: Record<string, string> = {
  under: 'text-red-400',
  over:  'text-sky-400',
  none:  'text-zinc-400',
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function EstimationRunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const data = await apiFetch<EstimationRunDetail>(`/api/estimation/runs/${id}`)

  if (!data || data.error || !data.run) notFound()

  const { run, estimate, evaluation, recommendation, reservation, settlement,
          pricing_version, task_type, events, derived } = data

  const hasEval     = evaluation !== null
  const hasComplete = hasEval && evaluation!.telemetry_status === 'complete'

  const errorSev = hasComplete
    ? errorSeverity(evaluation!.percentage_error)
    : 'ok'

  const direction = derived?.signedErrorUsd != null
    ? derived.signedErrorUsd > 0 ? 'under' : 'over'
    : 'none'

  const features = estimate?.estimation_features_snapshot

  return (
    <div className="p-6 space-y-8 max-w-4xl">

      {/* Back link */}
      <Link
        href="/dashboard/estimation"
        className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300 transition-colors w-fit"
      >
        <ArrowLeft className="h-4 w-4" />
        Estimation Overview
      </Link>

      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="space-y-1">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-semibold text-zinc-100 font-mono">
            {id.slice(0, 8)}…
          </h1>
          <span className="text-xs font-mono bg-zinc-800 text-zinc-400 rounded px-2 py-0.5">
            {task_type?.code ?? run.task_complexity_bucket ?? '—'}
          </span>
          <span className="text-xs font-mono bg-zinc-800 text-zinc-400 rounded px-2 py-0.5">
            {run.task_complexity_bucket}
          </span>
          {estimate && (
            <span className="text-xs font-mono bg-zinc-800 text-zinc-400 rounded px-2 py-0.5">
              {estimate.provider}/{estimate.model}
            </span>
          )}
        </div>
        <p className="text-sm text-zinc-500">
          {run.started_at ? formatDateTime(run.started_at) : '—'}
          {task_type ? ` · ${task_type.label}` : ''}
        </p>
      </div>

      {/* ── Estimation Outcome ─────────────────────────────────────── */}
      <section className="space-y-3">
        <SectionHeader>Estimation Outcome</SectionHeader>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Estimated p50" value={estimate ? formatUsd(estimate.cost_p50_usd) : '—'} mono />
          <Stat label="Estimated p95" value={estimate ? formatUsd(estimate.cost_p95_usd) : '—'} mono />
          <Stat
            label="Actual cost"
            value={hasEval ? formatUsd(evaluation!.actual_cost_usd) : '—'}
            mono
          />
          <div className="rounded-lg bg-zinc-900 border border-zinc-800 p-3">
            <p className="text-xs text-zinc-500 mb-1">Error</p>
            {hasComplete ? (
              <div className="space-y-0.5">
                <p className={`text-sm font-medium font-mono ${SEVERITY_COLORS[errorSev]}`}>
                  {formatErrorPct(evaluation!.percentage_error)}
                </p>
                <p className={`text-xs font-semibold ${ERROR_DIRECTION_COLORS[direction]}`}>
                  {direction === 'under' ? '↑ UNDERESTIMATED' : direction === 'over' ? '↓ OVERESTIMATED' : '—'}
                </p>
              </div>
            ) : (
              <p className="text-sm text-zinc-500">
                {hasEval ? `telemetry: ${evaluation!.telemetry_status}` : 'no evaluation yet'}
              </p>
            )}
          </div>
        </div>

        {/* Band containment callout */}
        {hasComplete && derived && (
          <div className={`rounded-lg border px-4 py-3 flex items-center gap-3 ${
            derived.withinP95Band
              ? 'border-emerald-900/50 bg-emerald-950/20'
              : 'border-red-900/50 bg-red-950/20'
          }`}>
            <span className={`h-2 w-2 rounded-full shrink-0 ${derived.withinP95Band ? 'bg-emerald-500' : 'bg-red-500'}`} />
            <span className={`text-sm ${derived.withinP95Band ? 'text-emerald-300' : 'text-red-300'}`}>
              {derived.withinP95Band
                ? `Actual cost fell within the p95 band (${formatUsd(estimate?.cost_p95_usd)})`
                : `Actual cost exceeded the p95 band (${formatUsd(estimate?.cost_p95_usd)}) — tail scenario`
              }
            </span>
            {derived.failureMode !== 'within_tolerance' && derived.failureMode !== 'insufficient_data' && (
              <span className="ml-auto text-xs text-zinc-500 shrink-0">
                Failure mode: <span className="text-zinc-300">{derived.failureMode}</span>
              </span>
            )}
          </div>
        )}
      </section>

      {/* ── Failure Mode ───────────────────────────────────────────── */}
      {hasComplete && derived && derived.failureMode !== 'within_tolerance' && derived.failureMode !== 'insufficient_data' && (
        <section className="space-y-3">
          <SectionHeader>Root Cause</SectionHeader>
          <div className="rounded-lg border border-amber-900/40 bg-amber-950/10 p-4 space-y-2">
            <p className="text-sm font-semibold text-amber-300">
              {FAILURE_MODE_LABELS[derived.failureMode]}
            </p>
            <p className="text-xs text-zinc-500 font-mono">{derived.failureMode}</p>
          </div>
        </section>
      )}

      {/* ── Token Prediction ───────────────────────────────────────── */}
      {hasComplete && estimate && evaluation && (
        <section className="space-y-3">
          <SectionHeader>Token Prediction</SectionHeader>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-6 px-4 py-2 border-b border-zinc-800">
              <span className="text-xs text-zinc-500">Dimension</span>
              <span className="text-xs text-zinc-500 text-right">Estimated</span>
              <span className="text-xs text-zinc-500 text-right">Actual</span>
              <span className="text-xs text-zinc-500 text-right w-20">Error</span>
            </div>
            {[
              {
                label:     'Input tokens',
                estimated: formatTokens(estimate.tokens_in_p50),
                actual:    formatTokens(evaluation.tokens_in_actual),
                errorPct:  derived?.tokenInErrorPct ?? null,
              },
              {
                label:     'Output tokens',
                estimated: formatTokens(estimate.tokens_out_p50),
                actual:    formatTokens(evaluation.tokens_out_actual),
                errorPct:  derived?.tokenOutErrorPct ?? null,
              },
            ].map(row => {
              const sev = errorSeverity(row.errorPct)
              return (
                <div key={row.label} className="grid grid-cols-[1fr_auto_auto_auto] gap-x-6 px-4 py-2.5 border-b border-zinc-800/60 last:border-0 items-center">
                  <span className="text-sm text-zinc-300">{row.label}</span>
                  <span className="text-sm font-mono text-zinc-400 text-right">{row.estimated}</span>
                  <span className="text-sm font-mono text-zinc-200 text-right">{row.actual}</span>
                  <span className={`text-sm font-mono text-right w-20 ${SEVERITY_COLORS[sev]}`}>
                    {formatErrorPct(row.errorPct)}
                  </span>
                </div>
              )
            })}
          </div>

          {/* Root cause interpretation */}
          {derived?.tokenInErrorPct !== null && Math.abs(derived?.tokenInErrorPct ?? 0) > 100 && (
            <p className="text-xs text-zinc-500 pl-1">
              {Math.abs(derived?.tokenInErrorPct ?? 0) > Math.abs(derived?.tokenOutErrorPct ?? 0)
                ? '→ Root cause: input size was the primary driver of error, not output expansion.'
                : '→ Root cause: output expansion was the primary driver — agent generated far more tokens than heuristic predicted.'
              }
            </p>
          )}
        </section>
      )}

      {/* ── Feature Snapshot ───────────────────────────────────────── */}
      {features && (
        <section className="space-y-3">
          <SectionHeader>Estimation Feature Snapshot</SectionHeader>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
            {(
              [
                { key: 'feature_schema_version',       label: 'Feature schema version' },
                { key: 'task_type_code',                label: 'Task type' },
                { key: 'task_complexity_bucket',        label: 'Complexity bucket' },
                { key: 'prompt_chars',                  label: 'Prompt chars' },
                { key: 'context_ref_count',             label: 'Context refs' },
                { key: 'artifact_ref_count',            label: 'Artifact refs' },
                { key: 'declared_max_steps',            label: 'Declared max steps' },
                { key: 'declared_child_runs',           label: 'Declared child runs' },
                { key: 'context_window_requested_pct',  label: 'Context window requested' },
                { key: 'tools_enabled',                 label: 'Tools enabled' },
              ] satisfies Array<{ key: keyof EstimationFeatures; label: string }>
            ).map(({ key, label }) => {
              const rawVal = features?.[key]
              const val = Array.isArray(rawVal)
                ? rawVal.join(', ') || '(none)'
                : String(rawVal ?? '—')

              // Flag known Phase 1 blind spots in amber
              const isBlindSpot = (key === 'prompt_chars' && rawVal === 0)
                || (key === 'context_ref_count' && rawVal === 0)

              return (
                <div key={key} className="flex items-center justify-between px-4 py-2.5 border-b border-zinc-800/60 last:border-0">
                  <span className="text-xs text-zinc-500">{label}</span>
                  <span className={`text-xs font-mono ${isBlindSpot ? 'text-amber-400' : 'text-zinc-300'}`}>
                    {val}
                    {isBlindSpot && ' ⚠'}
                  </span>
                </div>
              )
            })}
          </div>
          {features.prompt_chars === 0 && (
            <p className="text-xs text-amber-500/80 pl-1">
              ⚠ prompt_chars = 0: the ingest endpoint cannot observe prompt content at run_started time.
              Input token estimate used system overhead only (~250 tokens). This is the primary source
              of error for large-context tasks in Phase 1.
            </p>
          )}
        </section>
      )}

      {/* ── Why This Estimate? ─────────────────────────────────────── */}
      {derived?.explanation && derived.explanation.length > 0 && (
        <section className="space-y-3">
          <SectionHeader>Why this estimate?</SectionHeader>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 space-y-1.5">
            {derived.explanation.map((line, i) => (
              <p key={i} className={`text-xs font-mono ${line.startsWith('⚠') ? 'text-amber-400' : 'text-zinc-400'}`}>
                {line}
              </p>
            ))}
          </div>
        </section>
      )}

      {/* ── Pricing Table ──────────────────────────────────────────── */}
      {estimate && (
        <section className="space-y-3">
          <SectionHeader>Pricing Table Used</SectionHeader>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm text-zinc-200">{pricing_version?.version ?? '—'}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                pricing_version?.status === 'active' ? 'bg-emerald-950 text-emerald-400' : 'bg-zinc-800 text-zinc-500'
              }`}>{pricing_version?.status ?? '—'}</span>
            </div>
            {estimate.pricing_snapshot?.rates && (
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs font-mono">
                <span className="text-zinc-500">Input / 1k tokens</span>
                <span className="text-zinc-300">${estimate.pricing_snapshot.rates.input_per_1k_tokens_usd.toFixed(4)}</span>
                <span className="text-zinc-500">Output / 1k tokens</span>
                <span className="text-zinc-300">${estimate.pricing_snapshot.rates.output_per_1k_tokens_usd.toFixed(4)}</span>
                <span className="text-zinc-500">Cached input / 1k</span>
                <span className="text-zinc-300">${estimate.pricing_snapshot.rates.cached_input_per_1k_tokens_usd.toFixed(5)}</span>
              </div>
            )}
            {hasComplete && derived && !derived.withinP95Band && derived.failureMode !== 'pricing_table_stale' && (
              <p className="text-xs text-zinc-500">
                Pricing table was correct — error was in token prediction, not rates.
              </p>
            )}
            {derived?.failureMode === 'pricing_table_stale' && (
              <p className="text-xs text-amber-400">
                ⚠ Token prediction was accurate but cost error was large — check if pricing table rates are current.
              </p>
            )}
          </div>
        </section>
      )}

      {/* ── Four Artifact Cards ────────────────────────────────────── */}
      <section className="space-y-3">
        <SectionHeader>Artifacts</SectionHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">

          {/* ART-001: Estimate */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 space-y-2">
            <ArtifactBadge label="ART-001" id={estimate?.id} tier="estimate_artifact" />
            {estimate ? (
              <div className="space-y-1 text-xs font-mono">
                <div className="flex justify-between"><span className="text-zinc-500">tier</span><span className="text-zinc-300">{estimate.estimation_tier}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">confidence</span><span className="text-zinc-300">{estimate.confidence}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">schema_version</span><span className="text-zinc-300">{estimate.schema_version}</span></div>
                {estimate.warnings.length > 0 && (
                  <div className="pt-1 space-y-0.5">
                    {estimate.warnings.map((w, i) => (
                      <p key={i} className="text-amber-500/80">⚠ {w}</p>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-zinc-600">No estimate artifact — pre-Phase 1 run</p>
            )}
          </div>

          {/* ART-002: Evaluation */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 space-y-2">
            <ArtifactBadge label="ART-002" id={evaluation?.id} tier="evaluation_artifact" />
            {evaluation ? (
              <div className="space-y-1 text-xs font-mono">
                <div className="flex justify-between"><span className="text-zinc-500">telemetry_status</span>
                  <span className={evaluation.telemetry_status === 'complete' ? 'text-emerald-400' : 'text-amber-400'}>
                    {evaluation.telemetry_status}
                  </span>
                </div>
                <div className="flex justify-between"><span className="text-zinc-500">eval_algorithm</span><span className="text-zinc-300">{evaluation.eval_algorithm_version}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">is_recomputable</span>
                  <span className={evaluation.is_recomputable ? 'text-emerald-400' : 'text-red-400'}>
                    {String(evaluation.is_recomputable)}
                  </span>
                </div>
                <div className="flex justify-between"><span className="text-zinc-500">is_outlier</span><span className="text-zinc-300">{String(evaluation.is_outlier)}</span></div>
                {evaluation.failure_mode && (
                  <div className="flex justify-between"><span className="text-zinc-500">failure_mode</span><span className="text-amber-400">{evaluation.failure_mode}</span></div>
                )}
              </div>
            ) : (
              <p className="text-xs text-zinc-600">No evaluation artifact yet</p>
            )}
          </div>

          {/* ART-007: Recommendation */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 space-y-2">
            <ArtifactBadge label="ART-007" id={recommendation?.id as string} tier="recommendation_artifact" />
            {recommendation ? (
              <div className="space-y-1 text-xs font-mono">
                <div className="flex justify-between"><span className="text-zinc-500">routing_mode</span><span className="text-zinc-300">{recommendation.routing_mode as string}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">selection_mode</span><span className="text-zinc-300">{recommendation.model_selection_mode as string}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">selected</span><span className="text-zinc-300">{recommendation.selected_provider as string}/{recommendation.selected_model as string}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">cold_start</span><span className="text-zinc-300">{String(recommendation.cold_start_model_selected)}</span></div>
              </div>
            ) : (
              <p className="text-xs text-zinc-600">No recommendation artifact</p>
            )}
          </div>

          {/* ART-005/006: Reservation + Settlement */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 space-y-2">
            <ArtifactBadge label="ART-005/006" id={reservation?.id as string} tier="reservation + settlement" />
            {reservation ? (
              <div className="space-y-1 text-xs font-mono">
                <div className="flex justify-between"><span className="text-zinc-500">reserved_usd</span><span className="text-zinc-300">{formatUsd(reservation.reserved_usd as number)}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">tier</span><span className="text-zinc-300">{reservation.reservation_tier as string}</span></div>
                <div className="flex justify-between"><span className="text-zinc-500">status</span>
                  <span className={reservation.status === 'settled' ? 'text-emerald-400' : 'text-zinc-300'}>
                    {reservation.status as string}
                  </span>
                </div>
                {settlement && (
                  <>
                    <div className="border-t border-zinc-800 mt-1 pt-1" />
                    <div className="flex justify-between"><span className="text-zinc-500">actual_cost_usd</span><span className="text-zinc-200">{formatUsd(settlement.actual_cost_usd as number)}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">settlement_type</span><span className="text-zinc-300">{settlement.settlement_type as string}</span></div>
                    <div className="flex justify-between"><span className="text-zinc-500">settlement_source</span><span className="text-zinc-300">{settlement.settlement_source as string}</span></div>
                    {reservation.reserved_usd !== null && settlement.actual_cost_usd !== null && (
                      <div className="flex justify-between">
                        <span className="text-zinc-500">overrun vs reservation</span>
                        <span className={`${(settlement.actual_cost_usd as number) > (reservation.reserved_usd as number) ? 'text-red-400' : 'text-emerald-400'}`}>
                          {formatUsd((settlement.actual_cost_usd as number) - (reservation.reserved_usd as number))}
                        </span>
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <p className="text-xs text-zinc-600">No reservation</p>
            )}
          </div>
        </div>
      </section>

      {/* ── Replayability ──────────────────────────────────────────── */}
      {derived && (
        <section className="space-y-3">
          <SectionHeader>Replayability &amp; Calibration Eligibility</SectionHeader>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 divide-y divide-zinc-800">
            {[
              {
                label: 'Feature snapshot present',
                pass:  estimate?.estimation_features_snapshot !== null,
                detail:'Required to re-run estimator with different calibration',
              },
              {
                label: 'Pricing table resolvable',
                pass:  Boolean(estimate?.pricing_table_version_id),
                detail:'Pricing snapshot stored in artifact — rates are recoverable',
              },
              {
                label: 'Evaluation is_recomputable',
                pass:  Boolean(evaluation?.is_recomputable),
                detail:'Actuals can be re-derived from raw telemetry',
              },
              {
                label: 'Telemetry complete',
                pass:  evaluation?.telemetry_status === 'complete',
                detail:'All cost/token data present — safe for calibration training',
              },
            ].map(({ label, pass, detail }) => (
              <div key={label} className="flex items-center gap-3 px-4 py-3">
                <span className={`h-2 w-2 rounded-full shrink-0 ${pass ? 'bg-emerald-500' : 'bg-red-500'}`} />
                <div className="min-w-0">
                  <p className="text-sm text-zinc-200">{label}</p>
                  <p className="text-xs text-zinc-600 mt-0.5">{detail}</p>
                </div>
                <span className={`ml-auto text-xs font-bold shrink-0 ${pass ? 'text-emerald-500' : 'text-red-500'}`}>
                  {pass ? 'PASS' : 'FAIL'}
                </span>
              </div>
            ))}
          </div>
          <p className={`text-xs pl-1 ${derived.replayable ? 'text-emerald-500/80' : 'text-zinc-600'}`}>
            {derived.replayable
              ? '✓ This run can be used as a calibration training point when the bucket reaches its threshold.'
              : '✗ This run cannot be used for calibration — one or more replayability checks failed.'
            }
          </p>
        </section>
      )}

      {/* ── Raw Event Timeline ─────────────────────────────────────── */}
      {events.length > 0 && (
        <section className="space-y-3">
          <SectionHeader>Event Timeline</SectionHeader>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 divide-y divide-zinc-800">
            {events.map(ev => (
              <div key={ev.id} className="flex items-start gap-4 px-4 py-3">
                <span className="text-xs font-mono text-zinc-600 shrink-0 w-24 pt-0.5">
                  {ev.occurred_at ? formatDateTime(ev.occurred_at).split(' ')[1] : '—'}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs font-mono font-semibold ${
                      ev.severity === 'error' ? 'text-red-400'
                      : ev.severity === 'warning' ? 'text-amber-400'
                      : 'text-zinc-400'
                    }`}>{ev.event_type}</span>
                    {ev.message && (
                      <span className="text-xs text-zinc-500 truncate">{ev.message}</span>
                    )}
                  </div>
                  {(ev.tokens_in || ev.tokens_out || ev.cost_usd) && (
                    <div className="flex gap-3 mt-0.5 text-xs font-mono text-zinc-600">
                      {ev.tokens_in  && <span>in:{ev.tokens_in.toLocaleString()}</span>}
                      {ev.tokens_out && <span>out:{ev.tokens_out.toLocaleString()}</span>}
                      {ev.cost_usd   && <span>cost:{formatUsd(ev.cost_usd)}</span>}
                      {ev.duration_ms && <span>{ev.duration_ms}ms</span>}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Run identifiers ────────────────────────────────────────── */}
      <section className="space-y-2">
        <SectionHeader>Identifiers</SectionHeader>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Stat label="Run ID"                 value={id}                        mono />
          <Stat label="Estimate artifact ID"   value={estimate?.id ?? '—'}       mono />
          <Stat label="Evaluation artifact ID" value={evaluation?.id ?? '—'}     mono />
          <Stat label="Task classifier version" value={run.task_classifier_version ?? '—'} mono />
        </div>
      </section>

      {/* Link back to operational run detail */}
      <div className="pt-2 border-t border-zinc-800">
        <Link
          href={`/dashboard/runs/${id}`}
          className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          View operational run detail →
        </Link>
      </div>

    </div>
  )
}
