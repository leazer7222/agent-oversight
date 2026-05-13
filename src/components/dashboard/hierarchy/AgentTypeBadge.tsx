import { cn } from '@/lib/utils'

const variants: Record<string, string> = {
  orchestrator: 'bg-violet-500/10 text-violet-400 border border-violet-500/20',
  team:         'bg-blue-500/10 text-blue-400 border border-blue-500/20',
  worker:       'bg-zinc-500/10 text-zinc-400 border border-zinc-500/20',
}

const labels: Record<string, string> = {
  orchestrator: 'Orchestrator',
  team:         'Team',
  worker:       'Worker',
}

export function AgentTypeBadge({ type }: { type: string | null }) {
  const key = type ?? 'worker'
  const style = variants[key] ?? variants.worker
  const label = labels[key] ?? key

  return (
    <span className={cn('inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium leading-none', style)}>
      {label}
    </span>
  )
}
