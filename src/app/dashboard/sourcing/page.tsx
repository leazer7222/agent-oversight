import { apiFetch } from '@/lib/api/fetch'
import { SourcingWorkspace } from './workspace'
import type { Ops, Profile } from './model'
// The same file the worker reads when it writes a draft: what the emails may say.
import businessProfile from '../../../../agents/library/partnership-coordinator/business_profile.json'

/**
 * Facility sourcing workspace - server shell.
 *
 * Fetches one payload (`/api/sourcing/operations`, tenant resolved from the
 * session) and hands it to the client workspace, which renders the five views
 * Cameron works in: Overview, Facilities, Conversations, Decisions, Activity.
 * Every number on screen comes from that payload; nothing is hard-coded, and
 * prototype data stays labelled wherever it appears.
 */
export default async function SourcingPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; company?: string; facility?: string; thread?: string; filter?: string }>
}) {
  const sp = await searchParams
  const company = sp.company ?? ''
  const qs = company ? `?company=${encodeURIComponent(company)}` : ''
  const ops = await apiFetch<Ops>(`/api/sourcing/operations${qs}`)

  if (!ops) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <h1 className="text-xl font-semibold text-zinc-100">Facility sourcing</h1>
        <div className="mt-4 rounded-lg border border-rose-900/60 bg-rose-950/30 p-4 text-sm text-rose-200">
          <p className="font-medium">We could not load the workspace.</p>
          <p className="mt-1 text-rose-300/80">
            Your session may have expired, or you are not a member of a company yet. Try signing in
            again; if it persists, the operations API logged the reason on the server.
          </p>
          <a href="/login?next=%2Fdashboard%2Fsourcing" className="mt-3 inline-block text-rose-100 underline">Sign in again</a>
        </div>
      </div>
    )
  }

  return (
    <SourcingWorkspace
      ops={ops}
      initialTab={sp.tab ?? 'overview'}
      initialFacility={sp.facility ?? null}
      initialThread={sp.thread ?? null}
      initialFilter={sp.filter ?? 'all'}
      company={company}
      profile={businessProfile as Profile}
    />
  )
}
