import { Sidebar } from '@/components/dashboard/Sidebar'

/**
 * Dashboard shell. The sidebar is a fixed column from the md breakpoint up;
 * below that it collapses into a menu disclosure so a phone-width viewport
 * gives the page its full width (previously the 14rem sidebar consumed the
 * whole screen on mobile).
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100 md:flex-row">
      <div className="hidden md:block">
        <Sidebar />
      </div>
      <details className="border-b border-zinc-800 md:hidden">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-zinc-100 [&::-webkit-details-marker]:hidden">
          Agent Oversight
          <span className="rounded-md border border-zinc-800 px-2 py-0.5 text-xs font-normal text-zinc-400">Menu</span>
        </summary>
        <div className="border-t border-zinc-800">
          <Sidebar />
        </div>
      </details>
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}
