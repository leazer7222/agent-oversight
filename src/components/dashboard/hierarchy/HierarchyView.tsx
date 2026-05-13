'use client'

import { useState } from 'react'
import { TenantSection } from './TenantSection'
import { EmptyState } from '@/components/dashboard/EmptyState'
import type { TenantGroup } from '@/app/api/hierarchy/route'

interface Props {
  tenants: TenantGroup[]
}

export function HierarchyView({ tenants }: Props) {
  // The only client-side state on this page: which node IDs are collapsed.
  // Everything else is structural metadata passed from the server.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  function onToggle(id: string) {
    setCollapsed(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  if (tenants.length === 0) {
    return <EmptyState message="No agents registered" />
  }

  return (
    <div className="space-y-4">
      {tenants.map(tenant => (
        <TenantSection
          key={tenant.company_id}
          tenant={tenant}
          collapsed={collapsed}
          onToggle={onToggle}
        />
      ))}
    </div>
  )
}
