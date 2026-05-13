import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const styles: Record<string, string> = {
  completed: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  failed:    'bg-red-500/15 text-red-400 border-red-500/20',
  started:   'bg-blue-500/15 text-blue-400 border-blue-500/20',
  active:    'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  paused:    'bg-yellow-500/15 text-yellow-400 border-yellow-500/20',
  inactive:  'bg-zinc-500/15 text-zinc-400 border-zinc-500/20',
}

export function StatusBadge({ status }: { status: string | null }) {
  const s = status ?? 'unknown'
  return (
    <Badge
      variant="outline"
      className={cn('text-xs font-medium capitalize', styles[s] ?? 'bg-zinc-500/15 text-zinc-400 border-zinc-500/20')}
    >
      {s}
    </Badge>
  )
}
