import type { NextRequest } from 'next/server'
import { z } from 'zod'
import { createServiceRoleClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'

const PutSchema = z.object({
  project_tag: z.enum([
    'master-agentic-flow',
    'reformai',
    'notion-personal-os',
    'resume-career',
    'global',
  ]),
  current_state: z.string(),
  todo: z.string(),
  lessons: z.string(),
})

export async function PUT(request: NextRequest) {
  const secret = request.headers.get('x-agent-secret')
  if (!secret || secret !== process.env.INGEST_SECRET) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const parsed = PutSchema.safeParse(body)
  if (!parsed.success) {
    return Response.json(
      { error: 'Validation failed', issues: parsed.error.issues },
      { status: 422 }
    )
  }

  const supabase = createServiceRoleClient()
  const { project_tag, current_state, todo, lessons } = parsed.data

  const { error } = await supabase
    .from('project_state')
    .upsert(
      { project_tag, current_state, todo, lessons },
      { onConflict: 'project_tag' }
    )

  if (error) {
    return Response.json({ error: error.message }, { status: 500 })
  }

  return Response.json({ ok: true, project_tag }, { status: 200 })
}
