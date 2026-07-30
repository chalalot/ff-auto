import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'
import { configApi } from '@/api/config'
import { usePersonas, useVisionModels, useLoraOptions, useLastUsed } from '@/hooks/usePersonas'
import { useProjectId } from '@/hooks/useProjectId'
import { toast } from '@/hooks/useToast'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Loader2, Play, Upload } from 'lucide-react'
import { WorkflowParametersPanel } from '@/components/workspace/WorkflowParametersPanel'
import { ImageLibrary } from '@/components/workspace/ImageLibrary'
import { resolveDroppedFiles, uploadErrorMessage } from '@/lib/uploads'
import { DEFAULT_CONFIG } from '@/lib/configDefaults'
import { workflowsApi } from '@/api/workflows'
import {
  FALLBACK_KIND, groupsOf, kindsInGroup, pickWorkflow, resolveKind, workflowChoices,
} from '@/lib/workflowKinds'
import type { ProcessImageConfig, WorkflowKind, WorkflowParameters } from '@/types'

// What a workflow *is* — Type, Mode, and which controls each needs — is
// configured in Configure › Types and tagged per file in Configure › Workflows,
// not listed here. Adding a kind of workflow is a data change; this component
// only knows how to read the vocabulary.
//
// Nothing about the kind is sent to the server: the backend already tells T2I
// from I2I by whether a source image is present, so a kind field on the request
// would be a second source of truth.

// Drop the `image` override from a node, removing the node entry when empty.
const withoutImageOverride = (
  prev: Record<string, Record<string, unknown>>,
  nodeId: string,
): Record<string, Record<string, unknown>> => {
  if (prev[nodeId]?.image === undefined) return prev
  const node = { ...prev[nodeId] }
  delete node.image
  const next = { ...prev }
  if (Object.keys(node).length === 0) delete next[nodeId]
  else next[nodeId] = node
  return next
}

export const CreatePanel: React.FC = () => {
  const queryClient = useQueryClient()
  const projectId = useProjectId() ?? undefined
  // Unified library selection — all images live in processed/
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set())
  const [config, setConfig] = useState<Omit<ProcessImageConfig, 'image_path'>>(DEFAULT_CONFIG)
  // The selected kind's value, e.g. 'image_generation.t2i'. Empty until the
  // vocabulary loads, at which point it resolves to the group's first kind.
  const [kindValue, setKindValue] = useState<string>('')
  // T2I only: send the typed prompt to the prompt agent to be rewritten (via
  // Prompt Review) instead of straight to ComfyUI. Off by default — what you
  // type is what gets generated unless you ask for the rewrite.
  const [enhancePrompt, setEnhancePrompt] = useState(false)
  const [promptText, setPromptText] = useState('')
  const [overrides, setOverrides] = useState<Record<string, Record<string, unknown>>>({})
  const configInitializedRef = React.useRef(false)

  const { data: workflows = [] } = useQuery<string[]>({
    queryKey: ['workflows'],
    queryFn: workspaceApi.getWorkflows,
  })
  const { data: kinds = [] } = useQuery<WorkflowKind[]>({
    queryKey: ['workflow-kinds'],
    queryFn: workflowsApi.getKinds,
  })
  const { data: tags = {} } = useQuery({
    queryKey: ['workflow-tags'],
    queryFn: workflowsApi.getTags,
  })

  const groups = React.useMemo(() => groupsOf(kinds), [kinds])
  const group =
    groups.find(g => g.value === config.workflow_type)?.value ?? groups[0]?.value ?? ''
  const modes = React.useMemo(() => kindsInGroup(kinds, group), [kinds, group])
  // The vocabulary may not have arrived yet, or may have lost the remembered
  // kind; resolveKind always yields something the sidebar can render.
  const kind = kinds.length > 0 ? resolveKind(kinds, kindValue, group) : FALLBACK_KIND
  const needsImage = kind.needs_image
  const prompt = promptText.trim()
  // Which pipeline a Process press takes. With an image, today's rule holds (an
  // empty prompt means "let the agent write one from it"); without one there is
  // always a prompt, so the checkbox is the only thing that can ask for the agent.
  const useAIPipeline = kind.uses_ai && (needsImage ? !prompt : enhancePrompt)

  // Only the workflows tagged for this kind, plus any that nobody has tagged.
  const choices = React.useMemo(
    () => workflowChoices(workflows, tags, kind.value),
    [workflows, tags, kind.value],
  )
  const workflowName = pickWorkflow(choices, config.workflow_name || undefined)
  const {
    data: workflowParams = null,
    isLoading: paramsLoading,
    error: paramsError,
  } = useQuery<WorkflowParameters>({
    queryKey: ['workflow-params', workflowName],
    queryFn: () => workspaceApi.getWorkflowParameters(workflowName),
    enabled: Boolean(workflowName),
  })

  // Overrides are sparse (only user-edited inputs); clear them whenever a
  // new parameter set loads so edits don't leak across workflows.
  React.useEffect(() => {
    setOverrides({})
  }, [workflowParams])

  const { data: personas = [] } = usePersonas()
  const { data: visionModels = [] } = useVisionModels()
  const { data: loraOptions = [] } = useLoraOptions()
  const { data: lastUsed, isSuccess: lastUsedLoaded } = useLastUsed()

  const { data: library = [], refetch: refetchLibrary } = useQuery({
    queryKey: ['workspace', 'ref-images', projectId ?? 'all'],
    queryFn: () => workspaceApi.getRefImages({ project_id: projectId }),
  })

  // The LoadImage node whose `image` input mirrors the library selection —
  // the first one with an editable image input.
  const loadImageNodeId = React.useMemo(() => {
    if (!workflowParams) return null
    const node = workflowParams.nodes.find(
      n => n.class_type === 'LoadImage' && n.inputs.some(i => i.key === 'image' && !i.locked),
    )
    return node?.node_id ?? null
  }, [workflowParams])

  // Library grid → LoadImage dropdown: a single selected image becomes the
  // node's `image` override; multi-select clears it so batch dispatch keeps
  // the per-image patch (overrides are applied after it and would clobber
  // every run with one file). An empty selection leaves the pick alone — it
  // may be a deliberate dropdown choice, incl. a baked-in ComfyUI name.
  // (Declared after the overrides-reset effect above so that on a workflow
  // switch it re-applies the selection to the freshly cleared overrides.)
  React.useEffect(() => {
    if (!loadImageNodeId || selectedPaths.size === 0) return
    if (selectedPaths.size > 1) {
      setOverrides(prev => withoutImageOverride(prev, loadImageNodeId))
      return
    }
    const only = Array.from(selectedPaths)[0]
    const match = library.find(i => i.path === only)
    if (!match) return
    setOverrides(prev =>
      prev[loadImageNodeId]?.image === match.filename
        ? prev
        : { ...prev, [loadImageNodeId]: { ...prev[loadImageNodeId], image: match.filename } },
    )
  }, [selectedPaths, loadImageNodeId, workflowParams, library])

  // A library image picked in the LoadImage dropdown counts as the run image
  // when nothing is selected in the grid — both point at the same library.
  const overrideImagePath = React.useMemo(() => {
    if (!workflowParams) return null
    for (const node of workflowParams.nodes) {
      if (node.class_type !== 'LoadImage') continue
      const chosen = overrides[node.node_id]?.image
      if (typeof chosen === 'string' && chosen) {
        const match = library.find(i => i.filename === chosen)
        if (match) return match.path
      }
    }
    return null
  }, [workflowParams, overrides, library])

  const effectivePaths = React.useMemo(
    () =>
      // T2I dispatches no image even if a selection or LoadImage pick lingers.
      !needsImage
        ? []
        : selectedPaths.size > 0
          ? Array.from(selectedPaths)
          : overrideImagePath
            ? [overrideImagePath]
            : [],
    [needsImage, selectedPaths, overrideImagePath],
  )

  // What Process needs before it can run: an image, or — in T2I — a prompt.
  const canDispatch = needsImage ? effectivePaths.length > 0 : prompt.length > 0

  // Load last used config on mount — runs once when query resolves
  React.useEffect(() => {
    if (!lastUsedLoaded) return
    if (lastUsed) {
      // The kind is validated against the vocabulary when it renders
      // (resolveKind), not here — the kinds query may still be in flight, and a
      // value that no longer exists degrades to the group's first kind anyway.
      if (lastUsed.generation_mode) setKindValue(lastUsed.generation_mode)
      setEnhancePrompt(Boolean(lastUsed.enhance_prompt))
      setConfig(prev => ({
        ...prev,
        persona: lastUsed.persona || prev.persona,
        vision_model: lastUsed.vision_model || prev.vision_model,
        variation_count: lastUsed.variations ?? prev.variation_count,
        workflow_type: lastUsed.workflow_type || prev.workflow_type,
        workflow_name: lastUsed.workflow_name || prev.workflow_name,
      }))
    }
    configInitializedRef.current = true
  }, [lastUsedLoaded]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-save config whenever user changes it (debounced 600ms)
  React.useEffect(() => {
    if (!configInitializedRef.current) return
    const timer = setTimeout(() => {
      configApi.saveLastUsed({
        persona: config.persona,
        vision_model: config.vision_model,
        variations: config.variation_count,
        workflow_type: config.workflow_type,
        workflow_name: config.workflow_name || undefined,
        // Stored under the old field name: it holds the full kind value now
        // ('image_generation.t2i'), and resolveKind still accepts a bare 'i2i'
        // written by an earlier build.
        generation_mode: kind.value,
        enhance_prompt: enhancePrompt,
      })
    }, 600)
    return () => clearTimeout(timer)
  }, [config, kind.value, enhancePrompt])

  // Set first persona as default
  React.useEffect(() => {
    if (personas.length > 0 && !config.persona) {
      setConfig(prev => ({ ...prev, persona: personas[0].name }))
    }
  }, [personas, config.persona])

  // All images live in processed/ — always skip prepare
  const processMutation = useMutation({
    mutationFn: async () => {
      const paths = effectivePaths
      let taskIds: string[]
      let runIds: Array<string | null>
      if (!needsImage) {
        // T2I: one run, no source image. With the agent on, the typed text is a
        // brief for it to write from (→ Prompt Review); with it off, the text is
        // the prompt and goes straight to ComfyUI (→ Image Review).
        if (useAIPipeline) {
          const result = await workspaceApi.process({
            ...config,
            workflow_name: workflowName,
            workflow_overrides: overrides,
            brief: prompt,
            skip_prepare: true,
          })
          taskIds = [result.task_id]
          runIds = [result.run_id ?? null]
        } else {
          const result = await workspaceApi.runDirect({
            image_paths: [],
            workflow_name: workflowName,
            workflow_type: config.workflow_type,
            prompt,
            workflow_overrides: overrides,
          })
          taskIds = result.task_ids
          runIds = result.run_ids ?? []
        }
      } else if (!useAIPipeline) {
        const result = await workspaceApi.runDirect({
          image_paths: paths,
          workflow_name: workflowName,
          workflow_type: config.workflow_type,
          prompt: kind.uses_text && prompt ? prompt : undefined,
          workflow_overrides: overrides,
        })
        taskIds = result.task_ids
        runIds = result.run_ids ?? []
      } else if (paths.length === 1) {
        const result = await workspaceApi.process({ ...config, workflow_name: workflowName, workflow_overrides: overrides, image_path: paths[0], skip_prepare: true })
        taskIds = [result.task_id]
        runIds = [result.run_id ?? null]
      } else {
        const result = await workspaceApi.processBatch(paths, { ...config, workflow_name: workflowName, workflow_overrides: overrides, skip_prepare: true })
        taskIds = result.task_ids
        runIds = result.run_ids
      }
      return { taskIds, runIds, paths, useAIPipeline }
    },
    onSuccess: ({ taskIds, runIds, useAIPipeline }) => {
      // Immediately refresh the global active-tasks list so this session and
      // all other open sessions see the new tasks right away.
      queryClient.invalidateQueries({ queryKey: ['workspace', 'active-tasks'] })
      queryClient.invalidateQueries({ queryKey: ['workspace', 'executions'] })
      queryClient.invalidateQueries({ queryKey: ['pipeline-runs'] })
      queryClient.invalidateQueries({ queryKey: ['workspace', 'ref-images'] })
      // Dispatch used to yank a single run straight to its trace page. The rail
      // now carries the state, so say what happened and let the user follow it
      // only if they want to.
      const n = taskIds.length
      const runId = runIds.find(Boolean)
      toast({
        title: `Dispatched ${n} ${n === 1 ? 'job' : 'jobs'}`,
        description: useAIPipeline
          ? 'The prompt pipeline is writing prompts — they land in Prompt Review.'
          : 'ComfyUI is generating — results land in Image Review.',
        action: n === 1 && runId
          ? { label: 'Open run trace', to: `/pipeline-runs/${runId}` }
          : { label: 'Watch in Generating', to: '/flow?stage=generating' },
      })
    },
  })

  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const handleUpload = async (files: FileList | File[] | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadError(null)
    try {
      await workspaceApi.uploadRefImages(Array.from(files))
      queryClient.invalidateQueries({ queryKey: ['workspace', 'ref-images'] })
    } catch (err) {
      setUploadError(uploadErrorMessage(err))
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = async (dt: DataTransfer) => {
    setUploading(true)
    setUploadError(null)
    try {
      const files = await resolveDroppedFiles(dt)
      if (files.length === 0) {
        setUploadError('No image found in the dropped content')
        return
      }
      await workspaceApi.uploadRefImages(files)
      queryClient.invalidateQueries({ queryKey: ['workspace', 'ref-images'] })
    } catch (err) {
      setUploadError(uploadErrorMessage(err))
    } finally {
      setUploading(false)
    }
  }

  const toggleImage = (path: string) => {
    setSelectedPaths(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const clearSelection = () => {
    setSelectedPaths(new Set())
    // An explicit deselect-all also clears the mirrored LoadImage pick.
    if (loadImageNodeId) setOverrides(prev => withoutImageOverride(prev, loadImageNodeId))
  }

  /** Switch kind: re-pick the workflow from the new kind's tagged files. */
  const selectKind = (next: WorkflowKind) => {
    setKindValue(next.value)
    // Clearing the name lets pickWorkflow choose one tagged for the new kind,
    // rather than keeping a file that no longer fits.
    setConfig(p => ({ ...p, workflow_type: next.group, workflow_name: '' }))
    // A kind that needs no image hides the library, so drop the selection with
    // it rather than keeping an invisible image a later switch would resurrect.
    if (!next.needs_image) clearSelection()
  }

  const deleteMutation = useMutation({
    mutationFn: (filename: string) => workspaceApi.deleteRefImage(filename),
    onSuccess: (_, filename) => {
      setSelectedPaths(prev => {
        const next = new Set(prev)
        for (const p of next) {
          if (p.endsWith('/' + filename) || p === filename) next.delete(p)
        }
        return next
      })
      // A LoadImage pick pointing at the deleted file is now dangling.
      if (loadImageNodeId) {
        setOverrides(prev =>
          prev[loadImageNodeId]?.image === filename
            ? withoutImageOverride(prev, loadImageNodeId)
            : prev,
        )
      }
      queryClient.invalidateQueries({ queryKey: ['workspace', 'ref-images'] })
    },
  })

  return (
    <div className="flex h-full min-h-0">
      {/* Config Sidebar */}
      <aside className="w-72 border-r bg-card flex flex-col overflow-y-auto">
        <div className="p-4 border-b">
          <h2 className="font-semibold text-sm">Configuration</h2>
        </div>

        <div className="p-4 space-y-4 flex-1">
          {/* Workflow Type — the kinds' groups. Data, not a fixed list. */}
          <div className="space-y-2">
            <Label>Workflow Type</Label>
            <Select
              value={group}
              onValueChange={(v) => {
                // Land on the new group's first kind, which also re-picks the
                // workflow from the files tagged for it.
                const first = kindsInGroup(kinds, v)[0]
                if (first) selectKind(first)
                else setConfig(p => ({ ...p, workflow_type: v, workflow_name: '' }))
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {groups.map(g => (
                  <SelectItem key={g.value} value={g.value}>{g.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {/* With one kind in the group there is no Mode select to carry the
                hint, so it belongs here. */}
            {modes.length <= 1 && kind.hint && (
              <p className="text-xs text-muted-foreground">{kind.hint}</p>
            )}
          </div>

          {/* Mode — only for a type with more than one kind under it. */}
          {modes.length > 1 && (
            <div className="space-y-2">
              <Label>Mode</Label>
              <Select
                value={kind.value}
                onValueChange={(v) => {
                  const next = modes.find(m => m.value === v)
                  if (next) selectKind(next)
                }}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {modes.map(m => (
                    <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {kind.hint && <p className="text-xs text-muted-foreground">{kind.hint}</p>}
            </div>
          )}

          {/* Workflow JSON graph */}
          <div className="space-y-2">
            <Label>Workflow</Label>
            <Select
              value={workflowName}
              onValueChange={(v) => setConfig(p => ({ ...p, workflow_name: v }))}
            >
              <SelectTrigger><SelectValue placeholder="No workflow" /></SelectTrigger>
              <SelectContent>
                {choices.matching.map(w => (
                  <SelectItem key={w} value={w}>{w.replace(/\.json$/i, '')}</SelectItem>
                ))}
                {choices.untagged.length > 0 && (
                  <div className="px-2 py-1.5 text-xs text-muted-foreground">
                    {choices.matching.length > 0 ? 'Untagged' : 'Untagged — tag these in Configure › Workflows'}
                  </div>
                )}
                {choices.untagged.map(w => (
                  <SelectItem key={w} value={w}>{w.replace(/\.json$/i, '')}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {choices.matching.length === 0 && choices.untagged.length > 0 && (
              <p className="text-xs text-muted-foreground">
                No workflow is tagged “{kind.label}” yet — tag one in Configure › Workflows and
                this list will narrow to it.
              </p>
            )}
          </div>

          {/* Prompt text — goes to the graph's prompt node. With no source
              image it is the only input, so it stops being optional. */}
          {kind.uses_text && (
            <div className="space-y-2">
              <Label>
                Prompt{' '}
                <span className="text-muted-foreground text-xs">
                  {needsImage ? '(optional)' : '(required)'}
                </span>
              </Label>
              <Textarea
                placeholder={
                  !needsImage
                    ? enhancePrompt
                      ? 'What you want, in your own words — the agent writes the final prompt'
                      : 'The prompt, exactly as ComfyUI should receive it'
                    : kind.uses_ai
                      ? 'Leave empty to let the AI write the prompt from the selected image'
                      : 'Edit instruction, e.g. "rotate the camera to a low three-quarter view"'
                }
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                rows={3}
              />
            </div>
          )}

          {/* With no image for the agent to read, using it is a choice rather
              than a consequence of leaving the prompt empty. */}
          {kind.uses_ai && !needsImage && (
            <label className="flex items-start gap-2.5 cursor-pointer">
              <Checkbox
                checked={enhancePrompt}
                onCheckedChange={(v) => setEnhancePrompt(v === true)}
                className="mt-0.5"
              />
              <span className="space-y-0.5">
                <span className="block text-sm font-medium leading-none">Enhance with the prompt agent</span>
                <span className="block text-xs text-muted-foreground">
                  {enhancePrompt
                    ? 'Your text is a brief. The agent rewrites it with the persona’s identity lock, and it lands in Prompt Review first.'
                    : 'Your text goes to ComfyUI unchanged, straight to Image Review.'}
                </span>
              </span>
            </label>
          )}

          {/* Prompt-agent settings — only when a press will actually use it:
              with an image, an empty prompt hands over to the agent; without
              one, only while the checkbox is on. */}
          {kind.uses_ai && (needsImage || enhancePrompt) && (
            <>
              <Separator />

              {/* Persona */}
              <div className="space-y-2">
                <Label>Persona</Label>
                <Select value={config.persona} onValueChange={(v) => setConfig(p => ({ ...p, persona: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select persona" /></SelectTrigger>
                  <SelectContent>
                    {personas.map(p => (
                      <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* The model that writes the prompt. It reads the image in I2I;
                  in T2I there is nothing to look at, so don't call it a vision
                  model there. */}
              <div className="space-y-2">
                <Label>{needsImage ? 'Vision Model' : 'Prompt Model'}</Label>
                <Select value={config.vision_model} onValueChange={(v) => setConfig(p => ({ ...p, vision_model: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {visionModels.map(m => (
                      <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Variations */}
              <div className="space-y-2">
                <Label>Variations: {config.variation_count}</Label>
                <Slider
                  min={1} max={5} step={1}
                  value={[config.variation_count]}
                  onValueChange={([v]) => setConfig(p => ({ ...p, variation_count: v }))}
                />
              </div>
            </>
          )}

          <Separator />

          <WorkflowParametersPanel
            params={workflowParams}
            loading={paramsLoading}
            error={paramsError ? 'Failed to load workflow parameters' : null}
            loraOptions={loraOptions}
            imageOptions={library.map(i => i.filename)}
            imageThumbnailUrl={workspaceApi.getRefImageThumbnailUrl}
            values={overrides}
            onChange={(nodeId, key, value) => {
              setOverrides(prev => ({ ...prev, [nodeId]: { ...prev[nodeId], [key]: value } }))
              // LoadImage dropdown → library grid: select the matching
              // library image; a baked-in ComfyUI name matches nothing, so
              // clear the grid rather than leave it claiming another image.
              if (nodeId === loadImageNodeId && key === 'image') {
                const match =
                  typeof value === 'string' ? library.find(i => i.filename === value) : undefined
                setSelectedPaths(match ? new Set([match.path]) : new Set())
              }
            }}
            onReset={() => setOverrides({})}
          />
        </div>
      </aside>

      {/* Library + dispatch */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b flex items-center justify-end gap-2">
          {/* Dispatch failures used to be silent — a batch that 500s just
              stopped spinning, which read as "multi-select doesn't work". */}
          {processMutation.isError && (
            <span
              className="mr-auto text-xs text-destructive max-w-md truncate"
              title={uploadErrorMessage(processMutation.error, 'Dispatch failed')}
            >
              {uploadErrorMessage(processMutation.error, 'Dispatch failed')}
            </span>
          )}
          {selectedPaths.size > 0 ? (
            <Badge variant="secondary">{selectedPaths.size} selected</Badge>
          ) : effectivePaths.length > 0 ? (
            <Badge variant="secondary">from Load Image</Badge>
          ) : null}
          {/* T2I's blocker is an empty prompt, not an empty selection — say so,
              since the sidebar is the only place that can unblock it. */}
          {!canDispatch && !needsImage && (
            <span className="text-xs text-muted-foreground">Write a prompt to enable Process</span>
          )}
          <Button
            onClick={() => processMutation.mutate()}
            disabled={!canDispatch || processMutation.isPending}
            isLoading={processMutation.isPending}
          >
            <Play className="w-4 h-4 mr-2" />
            Process {effectivePaths.length > 0 ? `(${effectivePaths.length})` : ''}
          </Button>
        </div>

        {!needsImage ? (
          // This kind takes no source image, so the library would only be a decoy.
          <div className="flex-1 flex items-center justify-center px-8">
            <div className="max-w-sm text-center space-y-1.5">
              <p className="text-sm font-medium">{kind.label}</p>
              <p className="text-xs text-muted-foreground">
                No source image needed — the prompt in the sidebar is the whole input.
                {modes.length > 1 && ' Pick another mode to generate from one of your images instead.'}
              </p>
            </div>
          </div>
        ) : (
        <div className="flex-1 overflow-auto px-4 py-4">
          {/* Upload zone */}
          <label
            className="flex flex-col items-center justify-center w-full mb-4 p-6 border-2 border-dashed border-muted-foreground/30 rounded-lg cursor-pointer hover:border-primary/50 hover:bg-muted/30 transition-colors"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); void handleDrop(e.dataTransfer) }}
          >
            <input type="file" className="hidden" accept=".png,.jpg,.jpeg,.webp" multiple
              onChange={(e) => void handleUpload(e.target.files)} />
            {uploading
              ? <Loader2 className="w-6 h-6 animate-spin text-muted-foreground mb-2" />
              : <Upload className="w-6 h-6 text-muted-foreground mb-2" />}
            <p className="text-sm text-muted-foreground">
              {uploading ? 'Uploading...' : 'Drop images here or click to upload'}
            </p>
            <p className="text-xs text-muted-foreground/60 mt-1">PNG, JPG, JPEG, WEBP</p>
            {uploadError && <p className="text-xs text-destructive mt-1">{uploadError}</p>}
          </label>

          <ImageLibrary
            images={library}
            selectedPaths={selectedPaths}
            onToggle={toggleImage}
            onDelete={(filename) => deleteMutation.mutate(filename)}
            deletingFilename={deleteMutation.isPending ? (deleteMutation.variables as string) : null}
            onSelectAll={(paths) => setSelectedPaths(new Set(paths))}
            onClearSelection={clearSelection}
            onRefresh={() => refetchLibrary()}
          />
        </div>
        )}
      </div>
    </div>
  )
}
