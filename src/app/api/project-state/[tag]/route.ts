import type { NextRequest } from 'next/server'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ tag: string }> }
) {
  const secret = request.headers.get('x-agent-secret')
  if (!secret || secret !== process.env.INGEST_SECRET) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const { tag } = await params
  const supabase = createServiceRoleClient()

  const { data, error } = await supabase
    .from('project_state')
    .select('project_tag, current_state, todo, lessons, updated_at')
    .eq('project_tag', tag)
    .single()

  if (error || !data) {
    return Response.json({ error: 'Project not found' }, { status: 404 })
  }

  return Response.json(data, { status: 200 })
}
