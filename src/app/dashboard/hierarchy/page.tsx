import { createServiceRoleClient } from '@/lib/supabase/server'
import { HierarchyView } from '@/components/dashboard/hierarchy/HierarchyView'
import { buildTenantTree } from '@/app/api/hierarchy/route'
import type { TenantGroup } from '@/app/api/hierarchy/route'

export default async function HierarchyPage() {
  const supabase = createServiceRoleClient()
  const { data: rows } = await supabase
    .from('agents')
    .select(`
      id, name,
      agent_type, status,
      depth, parent_agent_id,
      company_id, model, last_run_at,
      companies ( name )
    `)
    .order('depth', { ascending: true })
    .order('name',  { ascending: true })

  const flat = (rows ?? []).map((row: any) => ({
    ...row,
    company_name: row.companies?.name ?? null,
  }))
  const tenants: TenantGroup[] = buildTenantTree(flat)

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
