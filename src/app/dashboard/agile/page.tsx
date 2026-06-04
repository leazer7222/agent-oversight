import { IntakeConsole } from '@/components/dashboard/IntakeConsole'

export const dynamic = 'force-dynamic'

export default function AgileIntakePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Agile Intake</h1>
        <p className="text-sm text-zinc-400">
          Submit a product idea, paragraph, PRD, ticket, feedback, or bug. The Product Clarification
          Agent normalizes it into a Clarification Brief and only asks questions when the intake cannot
          satisfy the contract. Requires the worker running:{' '}
          <code className="text-zinc-300">python agents/teams/agile/worker.py</code>
        </p>
      </div>
      <IntakeConsole />
    </div>
  )
}
