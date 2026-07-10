import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react'
import type { PipelineStepStatus, PipelineStepTrace } from '@/types/pipeline'
import { cn } from '@/lib/utils'

const STEP_LABELS: Record<string, string> = {
  vision_observation: 'Vision observation',
  analyst: 'Analyst',
  turbo_engineer: 'Turbo Engineer',
}

const statusLabel: Record<PipelineStepStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
}

function StepStatusIcon({ status }: { status: PipelineStepStatus }) {
  if (status === 'succeeded') return <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden="true" />
  if (status === 'running') return <Loader2 className="h-5 w-5 animate-spin text-blue-600" aria-hidden="true" />
  if (status === 'failed') return <XCircle className="h-5 w-5 text-red-600" aria-hidden="true" />
  return <Circle className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
}

export function pipelineStepLabel(stepKey: string) {
  return STEP_LABELS[stepKey] ?? stepKey.replaceAll('_', ' ')
}

export function PipelineRunTimeline({
  steps,
  selectedStepId,
  onSelect,
}: {
  steps: PipelineStepTrace[]
  selectedStepId: string | null
  onSelect: (stepId: string) => void
}) {
  return (
    <ol className="space-y-2" aria-label="Pipeline execution steps">
      {steps.map(step => {
        const selected = step.id === selectedStepId
        return (
          <li key={step.id}>
            <button
              type="button"
              aria-current={selected ? 'step' : undefined}
              onClick={() => onSelect(step.id)}
              className={cn(
                'flex min-h-16 w-full items-center gap-3 rounded-md border px-3 py-2 text-left transition-colors',
                selected ? 'border-blue-500 bg-blue-50' : 'border-border hover:bg-muted/50',
              )}
            >
              <StepStatusIcon status={step.status} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{pipelineStepLabel(step.step_key)}</span>
                <span className="block text-xs text-muted-foreground">{statusLabel[step.status]}</span>
              </span>
              <span className="font-mono text-xs text-muted-foreground">{String(step.sequence).padStart(2, '0')}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
