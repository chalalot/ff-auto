/**
 * What this workflow is, and where its inputs go.
 *
 * Tagging a file with the kinds it can serve is what lets the Create sidebar's
 * Workflow dropdown show only the graphs that fit the selected Type and Mode.
 * The two node bindings are the escape hatch from auto-detection: the dispatcher
 * otherwise takes the first CLIPTextEncode with a literal `text` input, which in
 * a graph with a negative prompt is a coin toss.
 */
import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CheckCircle, Loader2, Save } from 'lucide-react'
import { workflowsApi } from '@/api/workflows'
import { PROMPT_INPUT_KEYS, groupsOf, kindsInGroup, nodesWithInput } from '@/lib/workflowKinds'
import type { WorkflowGraph, WorkflowKind } from '@/types'

/** Sentinel for "no binding" — a Radix Select item cannot hold an empty value. */
const DETECT = '__detect__'

export const WorkflowTagsPanel: React.FC<{
  workflowName: string
  graph: WorkflowGraph | null
}> = ({ workflowName, graph }) => {
  const queryClient = useQueryClient()

  const { data: kinds = [], isLoading: kindsLoading } = useQuery<WorkflowKind[]>({
    queryKey: ['workflow-kinds'],
    queryFn: workflowsApi.getKinds,
  })
  const { data: tags = {} } = useQuery({
    queryKey: ['workflow-tags'],
    queryFn: workflowsApi.getTags,
  })

  const stored = tags[workflowName]
  const [selected, setSelected] = useState<string[]>([])
  const [promptNode, setPromptNode] = useState(DETECT)
  const [imageNode, setImageNode] = useState(DETECT)

  // Re-seed from the server whenever the file or its stored entry changes, so
  // switching workflows in the sidebar never shows the previous one's tags.
  // Adjusted during render rather than in an effect: this is the "reset state
  // when a prop changes" case, and an effect would render the wrong tags once
  // before correcting itself.
  const storedKey = `${workflowName}|${JSON.stringify(stored ?? null)}`
  const [seededFrom, setSeededFrom] = useState<string | null>(null)
  if (seededFrom !== storedKey) {
    setSeededFrom(storedKey)
    setSelected(stored?.kinds ?? [])
    setPromptNode(stored?.prompt_node || DETECT)
    setImageNode(stored?.image_node || DETECT)
  }

  // `text` or `prompt` — a Qwen text node uses the latter.
  const promptCandidates = useMemo(() => nodesWithInput(graph, PROMPT_INPUT_KEYS), [graph])
  const imageCandidates = useMemo(() => nodesWithInput(graph, 'image'), [graph])

  const dirty =
    JSON.stringify([...selected].sort()) !== JSON.stringify([...(stored?.kinds ?? [])].sort()) ||
    promptNode !== (stored?.prompt_node || DETECT) ||
    imageNode !== (stored?.image_node || DETECT)

  const saveMutation = useMutation({
    mutationFn: () =>
      workflowsApi.saveTags(workflowName, {
        kinds: selected,
        prompt_node: promptNode === DETECT ? null : promptNode,
        image_node: imageNode === DETECT ? null : imageNode,
      }),
    onSuccess: () => {
      // The Create sidebar reads both of these to build its dropdowns.
      void queryClient.invalidateQueries({ queryKey: ['workflow-tags'] })
      void queryClient.invalidateQueries({ queryKey: ['workflow-kinds'] })
    },
  })

  const toggle = (value: string) =>
    setSelected(prev =>
      prev.includes(value) ? prev.filter(v => v !== value) : [...prev, value],
    )

  const nodeSelect = (
    value: string,
    onChange: (v: string) => void,
    candidates: Array<{ id: string; label: string }>,
    detectLabel: string,
  ) => (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={DETECT}>{detectLabel}</SelectItem>
        {candidates.map(c => (
          <SelectItem key={c.id} value={c.id}>{c.label}</SelectItem>
        ))}
        {/* A binding saved against a node the graph no longer has would vanish
            from this list; keep it visible so it can be seen and corrected. */}
        {value !== DETECT && !candidates.some(c => c.id === value) && (
          <SelectItem value={value}>{value} · not in this graph</SelectItem>
        )}
      </SelectContent>
    </Select>
  )

  if (kindsLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="h-full space-y-6 overflow-y-auto pr-1">
      <div className="space-y-3">
        <div>
          <Label>Types this workflow can run as</Label>
          <p className="mt-1 text-xs text-muted-foreground">
            The Create sidebar lists a workflow only under the types it is tagged with.
            Untagged files stay listed everywhere, under their own heading.
          </p>
        </div>

        <div className="space-y-3">
          {groupsOf(kinds).map(group => (
            <div key={group.value} className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">{group.label}</p>
              <div className="space-y-1.5 pl-1">
                {kindsInGroup(kinds, group.value).map(kind => (
                  <label key={kind.value} className="flex cursor-pointer items-start gap-2.5">
                    <Checkbox
                      checked={selected.includes(kind.value)}
                      onCheckedChange={() => toggle(kind.value)}
                      className="mt-0.5"
                    />
                    <span className="space-y-0.5">
                      <span className="block text-sm leading-none">{kind.label}</span>
                      <span className="block font-mono text-[10px] text-muted-foreground">
                        {kind.value}
                        {kind.needs_image ? ' · needs an image' : ' · prompt only'}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-3 border-t pt-4">
        <div>
          <Label>Where the inputs go</Label>
          <p className="mt-1 text-xs text-muted-foreground">
            Leave these on detect unless the wrong node is being written — the
            dispatcher picks the first node that takes the input, which is not
            always the one you mean.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs">Prompt node</Label>
            {nodeSelect(promptNode, setPromptNode, promptCandidates, 'Detect (first CLIP text node)')}
            {promptCandidates.length === 0 && (
              <p className="text-xs text-muted-foreground">No node in this graph takes text.</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Image node</Label>
            {nodeSelect(imageNode, setImageNode, imageCandidates, 'Detect (first LoadImage)')}
            {imageCandidates.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No node in this graph loads an image — this graph is prompt-only.
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 border-t pt-4">
        <Button
          size="sm"
          className="h-8 text-xs"
          disabled={!dirty || saveMutation.isPending}
          isLoading={saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          <Save className="mr-1.5 h-3.5 w-3.5" />
          Save tags
        </Button>
        {saveMutation.isSuccess && !dirty && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <CheckCircle className="h-3.5 w-3.5 text-green-500" />
            Saved
          </span>
        )}
        {saveMutation.isError && (
          <span className="text-xs text-destructive">
            {(saveMutation.error as { response?: { data?: { detail?: string } } })?.response?.data
              ?.detail ?? 'Could not save tags'}
          </span>
        )}
      </div>
    </div>
  )
}
