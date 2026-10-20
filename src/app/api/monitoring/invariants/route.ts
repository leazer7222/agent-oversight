import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'
import { requireAdminOrDeny } from '@/lib/auth/require-admin'

export const runtime = 'nodejs'

export async function GET(request: NextRequest) {
  const denied = await requireAdminOrDeny(request)
  if (denied) return denied

  const supabase = createServiceRoleClient()

  const { data, error } = await supabase.rpc('invariant_report')

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  return Response.json(data)
}
