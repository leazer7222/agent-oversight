import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

export async function GET(_request: NextRequest) {
  const supabase = createServiceRoleClient()

  const { data, error } = await supabase.rpc('invariant_report')

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  return Response.json(data)
}
