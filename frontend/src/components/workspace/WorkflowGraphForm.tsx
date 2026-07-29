import React from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { Link2 } from 'lucide-react'
import type { WorkflowGraph } from '@/types'

/**
 * Structured editor over a ComfyUI API-format graph: one collapsible section per
 * node, one field per literal input.
 *
 * Deliberately *not* the WorkflowParametersPanel. That panel edits sparse
 * per-run overrides and greys out inputs the app owns at dispatch time (`text`,
 * `device`). Here the file itself is being authored, so those fields are exactly
 * what the user needs to reach — a baked-in negative prompt is a legitimate
 * thing to write. Structural changes (adding, removing or rewiring nodes) stay
 * in the raw JSON tab.
 */
interface Props {
  graph: WorkflowGraph
  onInputChange: (nodeId: string, key: string, value: unknown) => void
  onTitleChange: (nodeId: string, title: string) => void
}

/** Node ids are numeric strings in practice; sort as numbers, fall back to text. */
const sortNodeIds = (ids: string[]) =>
  [...ids].sort((a, b) => {
    const na = Number(a)
    const nb = Number(b)
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb
    return a.localeCompare(b)
  })

/** An array-valued input is a link to another node's output, not a value. */
const isConnection = (value: unknown) => Array.isArray(value)

export const WorkflowGraphForm: React.FC<Props> = ({ graph, onInputChange, onTitleChange }) => {
  const nodeIds = React.useMemo(() => sortNodeIds(Object.keys(graph)), [graph])

  if (nodeIds.length === 0) {
    return <p className="text-sm text-muted-foreground">This workflow has no nodes.</p>
  }

  return (
    <div className="space-y-2">
      {nodeIds.map(nodeId => {
        const node = graph[nodeId]
        const inputs = node?.inputs ?? {}
        const entries = Object.entries(inputs)
        const values = entries.filter(([, v]) => !isConnection(v))
        const links = entries.filter(([, v]) => isConnection(v))
        const title = node?._meta?.title || node?.class_type || nodeId

        return (
          <details
            key={nodeId}
            className="rounded-md border border-border/60 bg-card px-3 py-2"
            open={values.length > 0 && nodeIds.length <= 12}
          >
            <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
              <span className="font-mono text-[10px] text-muted-foreground bg-muted rounded px-1 py-0.5 shrink-0">
                {nodeId}
              </span>
              <span className="truncate">{title}</span>
              <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                {node?.class_type}
              </span>
            </summary>

            <div className="mt-3 space-y-3">
              <div className="space-y-0.5">
                <Label className="text-[11px] text-muted-foreground">title</Label>
                <Input
                  value={node?._meta?.title ?? ''}
                  placeholder={node?.class_type}
                  onChange={e => onTitleChange(nodeId, e.target.value)}
                  className="h-7 text-xs"
                />
              </div>

              {values.map(([key, value]) => (
                <NodeInputField
                  key={key}
                  inputKey={key}
                  value={value}
                  onChange={v => onInputChange(nodeId, key, v)}
                />
              ))}

              {links.length > 0 && (
                <div className="pt-1 space-y-1">
                  {links.map(([key, value]) => {
                    const [source, outputIndex] = value as [unknown, unknown]
                    const sourceId = String(source)
                    const sourceNode = graph[sourceId]
                    return (
                      <div
                        key={key}
                        className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
                      >
                        <Link2 className="w-3 h-3 shrink-0" />
                        <span className="font-mono">{key}</span>
                        <span>←</span>
                        <span className={sourceNode ? '' : 'text-destructive font-medium'}>
                          node {sourceId}
                          {sourceNode ? ` (${sourceNode.class_type})` : ' — missing'}
                        </span>
                        <span className="opacity-60">output {String(outputIndex)}</span>
                      </div>
                    )
                  })}
                  <p className="text-[10px] text-muted-foreground/70">
                    Connections are edited in the Raw JSON tab.
                  </p>
                </div>
              )}
            </div>
          </details>
        )
      })}
    </div>
  )
}

/** Renders the right control for a literal input, inferred from its value. */
const NodeInputField: React.FC<{
  inputKey: string
  value: unknown
  onChange: (v: unknown) => void
}> = ({ inputKey, value, onChange }) => {
  if (typeof value === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-xs">
        <Checkbox checked={value} onCheckedChange={c => onChange(Boolean(c))} />
        <span className="font-mono">{inputKey}</span>
      </label>
    )
  }

  if (typeof value === 'number') {
    const isInteger = Number.isInteger(value)
    return (
      <div className="space-y-0.5">
        <Label className="text-[11px]">{inputKey}</Label>
        <Input
          type="number"
          step={isInteger ? '1' : 'any'}
          value={String(value)}
          onChange={e => {
            const raw = e.target.value
            const n = isInteger ? parseInt(raw, 10) : parseFloat(raw)
            // Keep the raw text while mid-typing ("-", "1.") so the field
            // doesn't fight the user; validation happens on save.
            onChange(Number.isNaN(n) ? raw : n)
          }}
          className="h-7 text-xs"
        />
      </div>
    )
  }

  if (typeof value === 'string') {
    // Prompt-shaped values get room to breathe; everything else is one line.
    const multiline = value.includes('\n') || value.length > 80 || inputKey === 'text'
    return (
      <div className="space-y-0.5">
        <Label className="text-[11px]">{inputKey}</Label>
        {multiline ? (
          <Textarea
            value={value}
            onChange={e => onChange(e.target.value)}
            className="text-xs font-mono min-h-[72px]"
          />
        ) : (
          <Input
            value={value}
            onChange={e => onChange(e.target.value)}
            className="h-7 text-xs"
          />
        )}
      </div>
    )
  }

  // null / nested object — rare, and not safely editable as a single field.
  return (
    <div className="space-y-0.5">
      <Label className="text-[11px] text-muted-foreground">{inputKey}</Label>
      <Input value={JSON.stringify(value)} disabled className="h-7 text-xs font-mono" />
      <p className="text-[10px] text-muted-foreground">Edit this value in the Raw JSON tab.</p>
    </div>
  )
}
