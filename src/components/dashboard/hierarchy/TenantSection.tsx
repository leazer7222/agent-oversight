import { Building2 } from 'lucide-react'
import { AgentTreeNode } from './AgentTreeNode'
import type { TenantGroup } from '@/app/api/hierarchy/route'

function countAll(nodes: import('@/app/api/hierarchy/route').AgentTreeNode[]): number {
  return nodes.reduce((sum, n) => sum + 1 + countAll(n.children), 0)
}

interface Props {
  tenant: TenantGroup
  collapsed: Set<string>
  onToggle: (id: string) => void
}

export function TenantSection({ tenant, collapsed, onToggle }: Props) {
  const total = countAll(tenant.agents)

  return (
    // Each tenant is visually isolated — reinforces the isolated-tenant model.
    // No shared borders or visual connections between tenant sections.
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
      {/* Tenant header */}
      <div className="flex items-center gap-2.5 px-4 py-3 border-b border-zinc-800 bg-zinc-900/80">
        <Building2 className="w-4 h-4 text-zinc-500 flex-shrink-0" />
        <span className="text-sm font-semibold text-zinc-200 tracking-tight">
          {tenant.company_name}
        </span>
        <span className="ml-auto text-xs text-zinc-600">
          {total} {total === 1 ? 'agent' : 'agents'}
        </span>
      </div>

      {/* Agent tree */}
      <div className="p-2">
        {tenant.agents.length === 0 ? (
          <p className="px-4 py-3 text-xs text-zinc-600">No agents registered.</p>
        ) : (
          tenant.agents.map(root => (
            <AgentTreeNode
              key={root.id}
              node={root}
              collapsed={collapsed}
              onToggle={onToggle}
              indentLevel={0}
            />
          ))
        )}
      </div>
    </div>
  )
}
