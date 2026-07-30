/**
 * The Workflow Type / Mode vocabulary, editable.
 *
 * This is the list the Create sidebar builds its two top selects from, so a new
 * kind of workflow — a video mode, an inpaint mode — is added here rather than
 * in the code. `group` is the Type; kinds sharing a group become the Modes under
 * it, which is how Image Generation ended up with I2I and T2I beneath it.
 *
 * The three flags are the whole reason the sidebar can be generic:
 *   needs image — off means Process fires on a prompt alone, and the library is
 *                 replaced by a note rather than shown as a decoy
 *   uses text   — off hides the prompt box entirely (an upscaler)
 *   uses agent  — off hides persona and model, and no press can reach the
 *                 prompt agent
 */
import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { CheckCircle, Loader2, Plus, RotateCcw, Save, Trash2 } from 'lucide-react'
import { workflowsApi } from '@/api/workflows'
import type { WorkflowKind } from '@/types'

const BLANK: WorkflowKind = {
  value: '',
  label: '',
  group: '',
  group_label: '',
  needs_image: true,
  uses_text: true,
  uses_ai: false,
  hint: '',
}

const errorDetail = (err: unknown, fallback: string): string => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

export const WorkflowKindsPanel: React.FC = () => {
  const queryClient = useQueryClient()
  const { data: stored = [], isLoading } = useQuery<WorkflowKind[]>({
    queryKey: ['workflow-kinds'],
    queryFn: workflowsApi.getKinds,
  })

  const [draft, setDraft] = useState<WorkflowKind[] | null>(null)
  const kinds = draft ?? stored
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(stored)

  // Drop a stale draft once the server's list changes under us (another tab, or
  // our own save landing). Adjusted during render rather than in an effect —
  // this is a state reset on new props, not a side effect.
  const storedKey = JSON.stringify(stored)
  const [seenStored, setSeenStored] = useState(storedKey)
  if (seenStored !== storedKey) {
    setSeenStored(storedKey)
    setDraft(null)
  }

  const saveMutation = useMutation({
    mutationFn: (next: WorkflowKind[]) => workflowsApi.saveKinds(next),
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: ['workflow-kinds'] })
      // A removed kind is dropped from every workflow's tags server-side.
      void queryClient.invalidateQueries({ queryKey: ['workflow-tags'] })
    },
  })

  const patch = (index: number, changes: Partial<WorkflowKind>) =>
    setDraft(kinds.map((k, i) => (i === index ? { ...k, ...changes } : k)))

  const remove = (index: number) => setDraft(kinds.filter((_, i) => i !== index))

  const add = () =>
    setDraft([
      ...kinds,
      // Seed the group from the last row: a new kind is usually another mode
      // under the type being worked on.
      {
        ...BLANK,
        group: kinds[kinds.length - 1]?.group ?? '',
        group_label: kinds[kinds.length - 1]?.group_label ?? '',
      },
    ])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b bg-card px-4 py-2.5">
        <div className="min-w-0">
          <p className="text-sm font-medium">Workflow types</p>
          <p className="text-xs text-muted-foreground">
            The Type and Mode selects in Create. Tag workflows with these under
            Configure › Workflows › Type &amp; inputs.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          {saveMutation.isSuccess && !dirty && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <CheckCircle className="h-3.5 w-3.5 text-green-500" />
              Saved
            </span>
          )}
          <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={add}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Add type
          </Button>
          <Button
            size="sm" variant="outline" className="h-7 text-xs"
            disabled={!dirty} onClick={() => setDraft(null)}
          >
            <RotateCcw className="mr-1 h-3.5 w-3.5" />
            Discard
          </Button>
          <Button
            size="sm" className="h-7 text-xs"
            disabled={!dirty || saveMutation.isPending}
            isLoading={saveMutation.isPending}
            onClick={() => saveMutation.mutate(kinds)}
          >
            <Save className="mr-1 h-3.5 w-3.5" />
            Save
          </Button>
        </div>
      </div>

      {saveMutation.isError && (
        <p className="border-b bg-destructive/5 px-4 py-2 text-xs text-destructive">
          {errorDetail(saveMutation.error, 'Could not save the types')}
        </p>
      )}

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {kinds.map((kind, index) => (
          <div key={index} className="space-y-3 rounded-lg border p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Value</Label>
                <Input
                  className="h-8 font-mono text-xs"
                  placeholder="image_generation.t2i"
                  value={kind.value}
                  onChange={e => patch(index, { value: e.target.value })}
                />
                <p className="text-[10px] text-muted-foreground">
                  Stored on tags and in the last-used config. Renaming it clears the
                  tags that point at the old name.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Label</Label>
                <Input
                  className="h-8 text-xs"
                  placeholder="T2I — prompt only"
                  value={kind.label}
                  onChange={e => patch(index, { label: e.target.value })}
                />
                <p className="text-[10px] text-muted-foreground">Shown in the Mode select.</p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Group</Label>
                <Input
                  className="h-8 font-mono text-xs"
                  placeholder="image_generation"
                  value={kind.group}
                  onChange={e => patch(index, { group: e.target.value })}
                />
                <p className="text-[10px] text-muted-foreground">
                  Types sharing a group become Modes under it.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Group label</Label>
                <Input
                  className="h-8 text-xs"
                  placeholder="Image Generation"
                  value={kind.group_label}
                  onChange={e => patch(index, { group_label: e.target.value })}
                />
                <p className="text-[10px] text-muted-foreground">Shown in the Workflow Type select.</p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              {([
                ['needs_image', 'Needs an image'],
                ['uses_text', 'Has a prompt box'],
                ['uses_ai', 'Can use the prompt agent'],
              ] as const).map(([field, label]) => (
                <label key={field} className="flex cursor-pointer items-center gap-2 text-xs">
                  <Checkbox
                    checked={kind[field]}
                    onCheckedChange={v => patch(index, { [field]: v === true })}
                  />
                  {label}
                </label>
              ))}
              <Button
                size="sm" variant="ghost"
                className="ml-auto h-7 text-xs text-destructive hover:text-destructive"
                onClick={() => remove(index)}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Remove
              </Button>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Hint</Label>
              <Textarea
                className="text-xs"
                rows={2}
                placeholder="One line under the select, saying where the inputs land."
                value={kind.hint}
                onChange={e => patch(index, { hint: e.target.value })}
              />
            </div>
          </div>
        ))}

        {kinds.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No types. Add at least one — the Create sidebar has nothing to offer without it.
          </p>
        )}
      </div>
    </div>
  )
}
