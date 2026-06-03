import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/dashboard/EmptyState'
import { formatDateTime } from '@/lib/utils'

export const dynamic = 'force-dynamic'

type Feature = { node_key: string; title: string; status: string; created_at: string }

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'outline'> = {
  ready: 'default', handed_off: 'secondary', scoping: 'outline', shelved: 'outline',
}

export default async function ScopingIndexPage() {
  const res = await apiFetch<{ features: Feature[]; backlog: Record<string, number | string | null> }>(
    '/api/scoping'
  )
  const features = res?.features ?? []
  const backlog = res?.backlog ?? {}

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Feature Scoping</h1>
        <p className="text-sm text-zinc-400">
          BA Scoping Agent output. Answer blocking questions and ratify proposed Concepts/Decisions to
          move a feature to scope-ready.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-sm text-zinc-400">Proposed Concepts</CardTitle></CardHeader>
          <CardContent className="text-2xl font-semibold text-zinc-100">
            {String(backlog.proposed_concepts ?? 0)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm text-zinc-400">Proposed Decisions</CardTitle></CardHeader>
          <CardContent className="text-2xl font-semibold text-zinc-100">
            {String(backlog.proposed_decisions ?? 0)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm text-zinc-400">Oldest Unratified</CardTitle></CardHeader>
          <CardContent className="text-sm text-zinc-300">
            {backlog.oldest_proposed_at ? formatDateTime(String(backlog.oldest_proposed_at)) : '-'}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Features</CardTitle></CardHeader>
        <CardContent>
          {features.length === 0 ? (
            <EmptyState message="No scoped features yet. Run the BA Scoping Agent to produce one." />
          ) : (
            <ul className="divide-y divide-zinc-800">
              {features.map((f) => (
                <li key={f.node_key} className="py-3">
                  <Link href={`/dashboard/scoping/${f.node_key}`}
                        className="flex items-center justify-between hover:opacity-80">
                    <div>
                      <div className="text-sm font-medium text-zinc-100">{f.title}</div>
                      <div className="text-xs text-zinc-500 font-mono">{f.node_key}</div>
                    </div>
                    <Badge variant={STATUS_VARIANT[f.status] ?? 'outline'}>{f.status}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
