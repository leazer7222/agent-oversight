export default function Loading() {
  return (
    <div className="mx-auto max-w-7xl animate-pulse space-y-6 p-6">
      <div className="h-7 w-56 rounded bg-zinc-800" />
      <div className="h-9 w-full max-w-xl rounded bg-zinc-900" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="h-20 rounded-lg border border-zinc-800 bg-zinc-900/50" />)}
      </div>
      <div className="h-64 rounded-lg border border-zinc-800 bg-zinc-900/50" />
      <p className="text-xs text-zinc-600">Loading the workspace from the database...</p>
    </div>
  )
}
