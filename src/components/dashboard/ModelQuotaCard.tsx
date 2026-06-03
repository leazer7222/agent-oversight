'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { RefreshCw } from 'lucide-react'

interface ModelQuota {
  name: string
  label?: string
  pct: number
  refreshesIn: string
}

const MOCK_MODELS: ModelQuota[] = [
  { name: 'Gemini 3.1 Pro', label: 'High', pct: 100, refreshesIn: '6 days, 23 hours' },
  { name: 'Gemini 3.1 Pro', label: 'Low', pct: 100, refreshesIn: '6 days, 23 hours' },
  { name: 'Gemini 3 Flash', pct: 95, refreshesIn: '6 days, 23 hours' },
  { name: 'Claude Sonnet 4.6', label: 'Thinking', pct: 100, refreshesIn: '7 days, 0 hour' },
  { name: 'Claude Opus 4.6', label: 'Thinking', pct: 100, refreshesIn: '7 days, 0 hour' },
  { name: 'GPT-OSS 120B', label: 'Medium', pct: 100, refreshesIn: '7 days, 0 hour' },
]

function QuotaBar({ pct }: { pct: number }) {
  const filled = Math.round(pct / 10)
  const color = pct > 50 ? 'bg-zinc-100' : pct > 20 ? 'bg-zinc-400' : 'bg-zinc-600'
  
  return (
    <div className="flex gap-px mt-1">
      {Array.from({ length: 10 }, (_, i) => (
        <div 
          key={i} 
          className={`h-1.5 flex-1 rounded-sm ${i < filled ? color : 'bg-zinc-800'}`} 
        />
      ))}
    </div>
  )
}

export function ModelQuotaCard() {
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-xs font-medium text-zinc-500 uppercase tracking-widest">
          Model Quota
        </CardTitle>
        <Button variant="outline" size="sm" className="h-8 bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700">
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-4 pt-2">
        <div className="rounded-lg border border-zinc-800/50 bg-zinc-900/30 p-4 space-y-6">
          {MOCK_MODELS.map((m, i) => (
            <div key={i} className="space-y-2">
              <div className="flex justify-between items-end">
                <div className="text-sm font-medium text-zinc-200">
                  {m.name} {m.label && <span className="text-zinc-500 ml-1">({m.label})</span>}
                </div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-tight">
                  Refreshes in {m.refreshesIn}
                </div>
              </div>
              <QuotaBar pct={m.pct} />
            </div>
          ))}
        </div>
        <p className="text-[10px] text-zinc-600">
          View your available model quota. Quota refreshes periodically based on your plan.
        </p>
      </CardContent>
    </Card>
  )
}
