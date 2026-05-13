export function CostLabel({ usd }: { usd: number | null }) {
  if (usd === null || usd === undefined) return <span className="text-zinc-500">—</span>
  if (usd === 0) return <span className="text-zinc-500">$0</span>
  if (usd < 0.0001) return <span>&lt;$0.0001</span>
  if (usd < 0.01)   return <span>${usd.toFixed(4)}</span>
  return <span>${usd.toFixed(4)}</span>
}
