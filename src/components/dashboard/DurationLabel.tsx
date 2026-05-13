export function DurationLabel({ ms }: { ms: number | null }) {
  if (ms === null || ms === undefined) return <span className="text-zinc-500">—</span>
  if (ms < 1000)    return <span>{ms}ms</span>
  if (ms < 60000)   return <span>{(ms / 1000).toFixed(1)}s</span>
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  if (ms < 3600000) return <span>{m}m {s}s</span>
  const h = Math.floor(ms / 3600000)
  const rm = Math.floor((ms % 3600000) / 60000)
  return <span>{h}h {rm}m</span>
}
