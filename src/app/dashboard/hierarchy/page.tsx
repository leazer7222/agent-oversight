import { apiFetch } from '@/lib/api/fetch'
import { HierarchyView } from '@/components/dashboard/hierarchy/HierarchyView'
import type { TenantGroup } from '@/app/api/hierarchy/route'

export default async function HierarchyPage() {
  const res = await apiFetch('/api/hierarchy')
  const tenants: TenantGroup[] = res?.tenants ?? []

  return (
    <div className="p-6 space-y-4 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Hierarchy</h1>
        <p className="text-sm text-zinc-500 mt-0.5">
          Operational topology — tenants, orchestrators, teams, and agents.
        </p>
      </div>

      <HierarchyView tenants={tenants} />
    </div>
  )
}
