import React from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import type { WorkflowParameters, WorkflowParamInput } from '@/types'

// Every editable input as { node_id: { key: value } }. Locked inputs excluded.
export function buildInitialOverrides(
  params: WorkflowParameters,
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {}
  for (const node of params.nodes) {
    const editable = node.inputs.filter(i => !i.locked)
    if (editable.length === 0) continue
    out[node.node_id] = {}
    for (const inp of editable) out[node.node_id][inp.key] = inp.value
  }
  return out
}

interface Props {
  params: WorkflowParameters | null
  loading: boolean
  error: string | null
  values: Record<string, Record<string, unknown>>
  onChange: (nodeId: string, key: string, value: unknown) => void
  onReset: () => void
}

export const WorkflowParametersPanel: React.FC<Props> = ({
  params, loading, error, values, onChange, onReset,
}) => {
  if (loading) return <p className="text-xs text-muted-foreground">Loading parameters…</p>
  if (error) return <p className="text-xs text-destructive">{error}</p>
  if (!params || params.nodes.length === 0)
    return <p className="text-xs text-muted-foreground">No parameters for this pipeline.</p>

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-semibold">Workflow Parameters</Label>
        <button className="text-xs text-muted-foreground hover:text-foreground" onClick={onReset}>
          reset
        </button>
      </div>
      {params.nodes.map(node => (
        <details key={node.node_id} className="rounded border border-border/60 px-2 py-1.5">
          <summary className="cursor-pointer text-xs font-medium">
            {node.title}
            <span className="ml-1 font-mono text-[10px] text-muted-foreground">{node.class_type}</span>
          </summary>
          <div className="mt-2 space-y-2">
            {node.inputs.map(inp => (
              <ParamField
                key={inp.key}
                input={inp}
                value={values[node.node_id]?.[inp.key]}
                onChange={v => onChange(node.node_id, inp.key, v)}
              />
            ))}
          </div>
        </details>
      ))}
    </div>
  )
}

const ParamField: React.FC<{
  input: WorkflowParamInput
  value: unknown
  onChange: (v: unknown) => void
}> = ({ input, value, onChange }) => {
  if (input.locked) {
    return (
      <div className="space-y-0.5" title={input.locked_reason ?? undefined}>
        <Label className="text-[11px] text-muted-foreground">{input.key}</Label>
        <Input value={String(input.value)} disabled className="h-7 text-xs" />
        {input.locked_reason && (
          <p className="text-[10px] text-muted-foreground">{input.locked_reason}</p>
        )}
      </div>
    )
  }
  if (input.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-[11px]">
        <Checkbox checked={Boolean(value)} onCheckedChange={c => onChange(Boolean(c))} />
        {input.key}
      </label>
    )
  }
  const isNumeric = input.type === 'integer' || input.type === 'number'
  return (
    <div className="space-y-0.5">
      <Label className="text-[11px]">{input.key}</Label>
      <Input
        type={isNumeric ? 'number' : 'text'}
        step={input.type === 'number' ? 'any' : undefined}
        value={value === undefined || value === null ? '' : String(value)}
        onChange={e => {
          const raw = e.target.value
          if (!isNumeric) return onChange(raw)
          const n = input.type === 'integer' ? parseInt(raw, 10) : parseFloat(raw)
          onChange(Number.isNaN(n) ? raw : n)
        }}
        className="h-7 text-xs"
      />
    </div>
  )
}
