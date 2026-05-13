import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

export interface AgentTreeNode {
  id: string
  name: string
  display_name: string | null
  agent_type: string | null
  status: string | null
  depth: number
  model: string | null
  last_run_at: string | null
  children: AgentTreeNode[]
}

export interface TenantGroup {
  company_id: string
  company_name: string
  agents: AgentTreeNode[]
}

function buildTree(rows: any[]): TenantGroup[] {
  // Group rows by company
  const byCompany = new Map<string, any[]>()
  for (const row of rows) {
    const key = row.company_id ?? '__unassigned__'
    if (!byCompany.has(key)) byCompany.set(key, [])
    byCompany.get(key)!.push(row)
  }

  const groups: TenantGroup[] = []

  for (const [companyId, companyRows] of byCompany) {
    // Build id → node map
    const nodeMap = new Map<string, AgentTreeNode>()
    for (const row of companyRows) {
      nodeMap.set(row.id, {
        id:           row.id,
        name:         row.name,
        display_name: row.display_name ?? null,
        agent_type:   row.agent_type  ?? null,
        status:       row.status      ?? null,
        depth:        row.depth       ?? 0,
        model:        row.model       ?? null,
        last_run_at:  row.last_run_at ?? null,
        children:     [],
      })
    }

    // Wire parent → children; orphans become roots
    const roots: AgentTreeNode[] = []
    for (const row of companyRows) {
      const node = nodeMap.get(row.id)!
      if (!row.parent_agent_id) {
        roots.push(node)
      } else if (nodeMap.has(row.parent_agent_id)) {
        nodeMap.get(row.parent_agent_id)!.children.push(node)
      } else {
        // Parent not found in result set — treat as root
        roots.push(node)
      }
    }

    // Sort roots and children: orchestrators first, then by name
    const sortNodes = (nodes: AgentTreeNode[]) => {
      nodes.sort((a, b) => {
        const aOrc = a.agent_type === 'orchestrator' ? 0 : 1
        const bOrc = b.agent_type === 'orchestrator' ? 0 : 1
        if (aOrc !== bOrc) return aOrc - bOrc
        return a.name.localeCompare(b.name)
      })
      for (const n of nodes) sortNodes(n.children)
    }
    sortNodes(roots)

    groups.push({
      company_id:   companyId,
      company_name: companyRows[0].company_name ?? companyId,
      agents:       roots,
    })
  }

  // Sort tenant groups by company name
  groups.sort((a, b) => a.company_name.localeCompare(b.company_name))

  return groups
}

/**
 * GET /api/hierarchy
 *
 * Returns the operational agent topology as a tree, grouped by tenant.
 * Intentionally omits run counts, token totals, and cost figures —
 * this route serves organizational structure and minimal operational
 * health signals only.
 */
export async function GET() {
  const supabase = createServiceRoleClient()

  const { data: rows, error } = await supabase
    .from('agents')
    .select(`
      id, name, display_name,
      agent_type, status,
      depth, parent_agent_id,
      company_id, model, last_run_at,
      companies ( name )
    `)
    .order('depth',  { ascending: true })
    .order('name',   { ascending: true })

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  // Flatten the companies join into company_name
  const flat = (rows ?? []).map((row: any) => ({
    ...row,
    company_name: row.companies?.name ?? null,
  }))

  const tenants = buildTree(flat)

  return Response.json({ tenants })
}
