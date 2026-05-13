'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Play,
  AlertCircle,
  DollarSign,
  Bot,
  Network,
} from 'lucide-react'

const nav = [
  { href: '/dashboard',           label: 'Overview',  icon: LayoutDashboard },
  { href: '/dashboard/agents',    label: 'Agents',    icon: Bot },
  { href: '/dashboard/hierarchy', label: 'Hierarchy', icon: Network },
  { href: '/dashboard/runs',      label: 'Runs',      icon: Play },
  { href: '/dashboard/errors',    label: 'Errors',    icon: AlertCircle },
  { href: '/dashboard/costs',     label: 'Costs',     icon: DollarSign },
]

export function Sidebar() {
  const path = usePathname()

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-zinc-800 bg-zinc-950">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-zinc-800">
        <Bot className="h-5 w-5 text-zinc-400" />
        <span className="text-sm font-semibold text-zinc-100 tracking-tight">
          Agent Oversight
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 p-2 pt-3">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = href === '/dashboard'
            ? path === '/dashboard'
            : path === href || path.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors',
                active
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200'
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-zinc-800">
        <p className="text-xs text-zinc-600">ReformAI Control Plane</p>
      </div>
    </aside>
  )
}
