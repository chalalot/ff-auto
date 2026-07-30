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
import type { ProcessImageConfig, WorkflowParameters } from '@/types'

// The three workflow categories. Each declares which input components the
// sidebar shows and which workflows/*.json file it starts from.
const WORKFLOW_TYPES: Array<{
  value: string
  label: string
  defaultWorkflow: string
  usesText: boolean
  usesAI: boolean
  hint: string
}> = [
  {
    value: 'image_generation',
    label: 'Image Generation',
    // Nested one level further — see GENERATION_MODES, which supplies the real
    // default workflow and hint for this type.
    defaultWorkflow: 'Z-image-control-net.json',
    usesText: true,
    usesAI: true,
    hint: '',
  },
  {
    value: 'image_upscaler',
    label: 'Image Upscaler',
    defaultWorkflow: 'SeedVR_Image_Upscaler.json',
    usesText: false,
    usesAI: false,
    hint: 'Image → LoadImage. Runs the workflow directly on each selected image.',
  },
  {
    value: 'multiangle_edit',
    label: 'Multiangle Edit',
    defaultWorkflow: 'Qwen-2511-Multi-Angle (1).json',
    usesText: true,
    usesAI: false,
    hint: 'Image → LoadImage, prompt → CLIP Text Encode. Camera angles are edited in Workflow Parameters.',
  },
]

const workflowTypeMeta = (value: string) =>
  WORKFLOW_TYPES.find(t => t.value === value) ?? WORKFLOW_TYPES[0]

// Image Generation is the one type with two shapes of input. T2I needs a prompt
// and nothing else; I2I needs a source image. Nothing about the mode is sent to
// the server — it already tells the two apart by whether a source image is
// present, so a mode field on the request would be a second source of truth.
export type GenerationMode = 't2i' | 'i2i'

const GENERATION_MODES: Array<{
  value: GenerationMode
  label: string
  defaultWorkflow: string
  needsImage: boolean
  hint: string
}> = [
  {
    value: 'i2i',
    label: 'I2I — from a source image',
    defaultWorkflow: 'Z-image-control-net.json',
    needsImage: true,
    hint: 'Image → LoadImage, prompt → CLIP Text Encode. Leave the prompt empty to let the AI write it from the image.',
  },
  {
    value: 't2i',
    label: 'T2I — prompt only',
    defaultWorkflow: 'ZIB-ZIT.json',
    needsImage: false,
    hint: 'Prompt → CLIP Text Encode. A T2I graph has no LoadImage node, so there is no image to select.',
  },
]

const generationModeMeta = (value: string) =>
  GENERATION_MODES.find(m => m.value === value) ?? GENERATION_MODES[0]

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
  const [genMode, setGenMode] = useState<GenerationMode>('i2i')
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

  const typeMeta = workflowTypeMeta(config.workflow_type)
  const isImageGen = config.workflow_type === 'image_generation'
  const modeMeta = generationModeMeta(genMode)
  // Only Image Generation is nested; every other type runs on a source image.
  const needsImage = !isImageGen || modeMeta.needsImage
  const defaultWorkflow = isImageGen ? modeMeta.defaultWorkflow : typeMeta.defaultWorkflow
  const prompt = promptText.trim()
  // Which pipeline a Process press takes. I2I keeps today's rule (an empty
  // prompt means "let the agent write one from the image"); T2I always has a
  // prompt, so the checkbox is the only thing that can ask for the agent.
  const useAIPipeline = isImageGen && (needsImage ? !prompt : enhancePrompt)

  // Selected workflow file: explicit choice → the type/mode default → first available.
  const workflowName =
    (config.workflow_name && workflows.includes(config.workflow_name) && config.workflow_name) ||
    (workflows.includes(defaultWorkflow) && defaultWorkflow) ||
    workflows[0] ||
    ''
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
      const knownType = WORKFLOW_TYPES.some(t => t.value === lastUsed.workflow_type)
      if (GENERATION_MODES.some(m => m.value === lastUsed.generation_mode)) {
        setGenMode(lastUsed.generation_mode as GenerationMode)
      }
      setEnhancePrompt(Boolean(lastUsed.enhance_prompt))
      setConfig(prev => ({
        ...prev,
        persona: lastUsed.persona || prev.persona,
        vision_model: lastUsed.vision_model || prev.vision_model,
        variation_count: lastUsed.variations ?? prev.variation_count,
        // Legacy values ("turbo"/"standard") fall back to the default type.
        workflow_type: knownType ? lastUsed.workflow_type! : prev.workflow_type,
        workflow_name: (knownType && lastUsed.workflow_name) || prev.workflow_name,
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
        generation_mode: genMode,
        enhance_prompt: enhancePrompt,
      })
    }, 600)
    return () => clearTimeout(timer)
  }, [config, genMode, enhancePrompt])

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
          prompt: typeMeta.usesText && prompt ? prompt : undefined,
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

  const selectGenerationMode = (mode: GenerationMode) => {
    setGenMode(mode)
    setConfig(p => ({ ...p, workflow_name: generationModeMeta(mode).defaultWorkflow }))
    // Leaving I2I hides the library, so drop the selection with it rather than
    // keeping an invisible image that a later switch back would resurrect.
    if (!generationModeMeta(mode).needsImage) clearSelection()
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
          {/* Workflow Type — drives which input components are shown */}
          <div className="space-y-2">
            <Label>Workflow Type</Label>
            <Select
              value={config.workflow_type}
              onValueChange={(v) => {
                // Image Generation's default graph depends on the mode, so read
                // it from there rather than from the type.
                const next =
                  v === 'image_generation'
                    ? generationModeMeta(genMode).defaultWorkflow
                    : workflowTypeMeta(v).defaultWorkflow
                setConfig(p => ({ ...p, workflow_type: v, workflow_name: next }))
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {WORKFLOW_TYPES.map(t => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!isImageGen && <p className="text-xs text-muted-foreground">{typeMeta.hint}</p>}
          </div>

          {/* Mode — Image Generation's one nested choice: T2I or I2I */}
          {isImageGen && (
            <div className="space-y-2">
              <Label>Mode</Label>
              <Select value={genMode} onValueChange={(v) => selectGenerationMode(v as GenerationMode)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {GENERATION_MODES.map(m => (
                    <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{modeMeta.hint}</p>
            </div>
          )}

          {/* Workflow JSON graph */}
          <div className="space-y-2">
            <Label>Workflow</Label>
            <Select
              value={workflowName}
              onValueChange={(v) => setConfig(p => ({ ...p, workflow_name: v }))}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {workflows.map(w => (
                  <SelectItem key={w} value={w}>{w.replace(/\.json$/i, '')}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Prompt text — goes to the CLIP Text Encode node (image gen / multiangle).
              In T2I it is the only input, so it stops being optional. */}
          {typeMeta.usesText && (
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
                    : typeMeta.usesAI
                      ? 'Leave empty to let the AI write the prompt from the selected image'
                      : 'Edit instruction, e.g. "rotate the camera to a low three-quarter view"'
                }
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                rows={3}
              />
            </div>
          )}

          {/* T2I has no image for the agent to read, so using it is a choice
              rather than a consequence of leaving the prompt empty. */}
          {isImageGen && !needsImage && (
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
              always in I2I (an empty prompt hands over to the agent), and in
              T2I only while the checkbox is on. */}
          {isImageGen && (needsImage || enhancePrompt) && (
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
          // T2I takes no source image, so the library would only be a decoy.
          <div className="flex-1 flex items-center justify-center px-8">
            <div className="max-w-sm text-center space-y-1.5">
              <p className="text-sm font-medium">Text to image</p>
              <p className="text-xs text-muted-foreground">
                No source image needed — the prompt in the sidebar is the whole input.
                Switch to I2I to generate from one of your images instead.
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
