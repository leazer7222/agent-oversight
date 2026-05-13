export function EmptyState({ message = 'No data' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center py-16 text-sm text-zinc-500">
      {message}
    </div>
  )
}
