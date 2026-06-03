import Link from 'next/link'
import { apiFetch } from '@/lib/api/fetch'
import { ScopingReview } from '@/components/dashboard/ScopingReview'
import { EmptyState } from '@/components/dashboard/EmptyState'

export const dynamic = 'force-dynamic'

export default async function ScopingFeaturePage({
  params,
}: {
  params: Promise<{ feature: string }>
}) {
  const { feature } = await params
  const res = await apiFetch<any>(`/api/scoping/${feature}`)

  if (!res || res.error || !res.detail?.feature) {
    return (
      <div className="space-y-4">
        <Link href="/dashboard/scoping" className="text-sm text-zinc-400 hover:text-zinc-200">&larr; Scoping</Link>
        <EmptyState message={res?.error ? `Error: ${res.error}` : `Feature ${feature} not found.`} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <Link href="/dashboard/scoping" className="text-sm text-zinc-400 hover:text-zinc-200">&larr; Scoping</Link>
      <ScopingReview
        feature={feature}
        detail={res.detail}
        readiness={res.readiness}
        upstream={res.upstream}
      />
    </div>
  )
}
