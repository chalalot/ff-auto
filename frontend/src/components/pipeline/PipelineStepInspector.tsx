import type { PipelineStepTrace } from '@/types/pipeline'
import { pipelineStepLabel } from './pipelineLabels'

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return 'No data'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

function PayloadSection({ label, value }: { label: string; value: unknown }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</h3>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 font-mono text-xs leading-5">
        {formatValue(value)}
      </pre>
    </section>
  )
}

function toolCallsFromContext(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  const toolCalls = (value as { tool_calls?: unknown }).tool_calls
  return Array.isArray(toolCalls) ? toolCalls : []
}

export function PipelineStepInspector({ step }: { step: PipelineStepTrace }) {
  const metadata = {
    model_name: step.model_name,
    usage: step.usage,
    started_at: step.started_at,
    finished_at: step.finished_at,
    status: step.status,
  }
  const toolCalls = toolCallsFromContext(step.rendered_context)

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted-foreground">Selected step</p>
        <h2 className="text-lg font-semibold">{pipelineStepLabel(step.step_key)}</h2>
      </div>
      <PayloadSection label="Input" value={step.input_payload} />
      <PayloadSection label="System Prompt" value={step.system_prompt} />
      <PayloadSection label="Context" value={step.rendered_context} />
      {toolCalls.length > 0 && <PayloadSection label="Tool Calls" value={toolCalls} />}
      <PayloadSection label="Output" value={step.output_payload ?? step.partial_output} />
      <PayloadSection label="Metadata" value={metadata} />
      {step.error && (
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-red-600">Error</h3>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md border border-red-200 bg-red-50 p-3 font-mono text-xs text-red-900">
            {formatValue(step.error)}
          </pre>
        </section>
      )}
    </div>
  )
}
