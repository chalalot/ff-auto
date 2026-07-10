import { ArrowLeft, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PipelineRunTimeline } from '@/components/pipeline/PipelineRunTimeline'
import { PipelineStepInspector } from '@/components/pipeline/PipelineStepInspector'
import { usePipelineRun } from '@/hooks/usePipelineRun'

function pipelineLabel(name: string) {
  return name.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function statusLabel(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Not started'
}

export function PipelineRunPage() {
  const { runId = '' } = useParams<{ runId: string }>()
  const { data: trace, isLoading, refreshError } = usePipelineRun(runId)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)

  const activeStepId = trace?.steps.some(step => step.id === selectedStepId)
    ? selectedStepId
    : trace?.steps.find(step => step.status === 'running')?.id ?? trace?.steps[0]?.id ?? null
  const selectedStep = trace?.steps.find(step => step.id === activeStepId) ?? null

  if (isLoading && !trace) {
    return <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading run trace...</div>
  }

  if (!trace) {
    return <div className="p-6 text-sm text-destructive">Unable to load this pipeline run.</div>
  }

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden">
      <header className="border-b px-6 py-4">
        <Link to="/workspace" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Workspace
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Pipeline run</p>
            <h1 className="text-2xl font-semibold">{pipelineLabel(trace.pipeline_name)}</h1>
          </div>
          <div className="text-right text-sm">
            <p className="font-medium">{statusLabel(trace.status)}</p>
            <p className="text-xs text-muted-foreground">Started {formatDate(trace.started_at)}</p>
          </div>
        </div>
        {refreshError && <p className="mt-3 text-xs text-amber-700">Refresh failed; showing the last available trace.</p>}
      </header>

      <div className="grid min-h-0 flex-1 gap-6 overflow-auto p-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <PipelineRunTimeline steps={trace.steps} selectedStepId={activeStepId} onSelect={setSelectedStepId} />
        <section className="min-w-0 rounded-md border bg-background p-5">
          {selectedStep ? <PipelineStepInspector step={selectedStep} /> : <p className="text-sm text-muted-foreground">No step data yet.</p>}
        </section>
      </div>
    </main>
  )
}
