'use client'

import Link from 'next/link'
import { ChevronRight, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { AgentTypeBadge } from './AgentTypeBadge'
import type { AgentTreeNode as AgentTreeNodeType } from '@/app/api/hierarchy/route'

// Status dot: communicates operational health, not execution state.
// Blue = operational/healthy (not green, which implies "currently running").
const statusDot: Record<string, string> = {
  active:     'bg-blue-400',
  paused:     'bg-amber-400',
  deprecated: 'bg-zinc-600',
  inactive:   'bg-zinc-600',
}

// Text weight decreases with hierarchy depth to reinforce visual structure.
const depthText: Record<number, string> = {
  0: 'text-zinc-100 font-medium',
  1: 'text-zinc-200 font-normal',
  2: 'text-zinc-300 font-normal',
}

function formatLastRun(ts: string | null): string {
  if (!ts) return '—'
  const diff = Date.now() - new Date(ts).getTime()
  const mins  = Math.floor(diff / 60_000)
  const hours = Math.floor(diff / 3_600_000)
  const days  = Math.floor(diff / 86_400_000)
  if (mins  < 1)   return 'just now'
  if (mins  < 60)  return `${mins}m ago`
  if (hours < 24)  return `${hours}h ago`
  if (days  < 30)  return `${days}d ago`
  return new Date(ts).toLocaleDateString()
}

interface Props {
  node: AgentTreeNodeType
  collapsed: Set<string>
  onToggle: (id: string) => void
  indentLevel: number
}

export function AgentTreeNode({ node, collapsed, onToggle, indentLevel }: Props) {
  const hasChildren = node.children.length > 0
  const isCollapsed = collapsed.has(node.id)
  const dot = statusDot[node.status ?? ''] ?? 'bg-zinc-600'
  const nameStyle = depthText[Math.min(indentLevel, 2)] ?? depthText[2]

  return (
    <div>
      {/* Node row */}
      <div
        className={cn(
          'group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-zinc-800/50 transition-colors',
          indentLevel > 0 && 'ml-5'
        )}
        style={{ paddingLeft: indentLevel > 0 ? `${indentLevel * 20 + 8}px` : '8px' }}
      >
        {/* Chevron toggle — only rendered if node has children */}
        <button
          onClick={() => hasChildren && onToggle(node.id)}
          className={cn(
            'flex-shrink-0 w-4 h-4 flex items-center justify-center rounded transition-colors',
            hasChildren
              ? 'text-zinc-500 hover:text-zinc-300 cursor-pointer'
              : 'text-transparent cursor-default pointer-events-none'
          )}
          aria-label={isCollapsed ? 'Expand' : 'Collapse'}
        >
          {hasChildren && (
            isCollapsed
              ? <ChevronRight className="w-3 h-3" />
              : <ChevronDown  className="w-3 h-3" />
          )}
        </button>

        {/* Status dot */}
        <span className={cn('flex-shrink-0 w-1.5 h-1.5 rounded-full', dot)} />

        {/* Name — links to agent detail */}
        <Link
          href={`/dashboard/agents/${node.id}`}
          className={cn('flex-1 min-w-0 text-sm truncate hover:text-blue-400 transition-colors', nameStyle)}
        >
          {node.name}
        </Link>

        {/* Type badge */}
        <AgentTypeBadge type={node.agent_type} />

        {/* Model — subtle monospace badge */}
        {node.model && (
          <span className="hidden sm:inline text-[10px] font-mono text-zinc-600 truncate max-w-[100px]">
            {node.model}
          </span>
        )}

        {/* Last run */}
        <span className="hidden md:inline text-[11px] text-zinc-600 w-16 text-right flex-shrink-0">
          {formatLastRun(node.last_run_at)}
        </span>
      </div>

      {/* Children — rendered beneath with left rail connector */}
      {hasChildren && !isCollapsed && (
        <div className="relative ml-5 border-l border-zinc-800/60">
          {node.children.map(child => (
            <AgentTreeNode
              key={child.id}
              node={child}
              collapsed={collapsed}
              onToggle={onToggle}
              indentLevel={indentLevel + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}
