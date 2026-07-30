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
    defaultWorkflow: 'Z-image-control-net.json',
    usesText: true,
    usesAI: true,
    hint: 'Image → LoadImage, prompt → CLIP Text Encode. Leave the prompt empty to let the AI write it from the image.',
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
  const [promptText, setPromptText] = useState('')
  const [overrides, setOverrides] = useState<Record<string, Record<string, unknown>>>({})
  const configInitializedRef = React.useRef(false)

  const { data: workflows = [] } = useQuery<string[]>({
    queryKey: ['workflows'],
    queryFn: workspaceApi.getWorkflows,
  })

  const typeMeta = workflowTypeMeta(config.workflow_type)
  // Selected workflow file: explicit choice → the type's default → first available.
  const workflowName =
    (config.workflow_name && workflows.includes(config.workflow_name) && config.workflow_name) ||
    (workflows.includes(typeMeta.defaultWorkflow) && typeMeta.defaultWorkflow) ||
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
      selectedPaths.size > 0
        ? Array.from(selectedPaths)
        : overrideImagePath
          ? [overrideImagePath]
          : [],
    [selectedPaths, overrideImagePath],
  )

  // Load last used config on mount — runs once when query resolves
  React.useEffect(() => {
    if (!lastUsedLoaded) return
    if (lastUsed) {
      const knownType = WORKFLOW_TYPES.some(t => t.value === lastUsed.workflow_type)
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
      })
    }, 600)
    return () => clearTimeout(timer)
  }, [config])

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
      const prompt = promptText.trim()
      // Image Generation without a manual prompt → AI prompt pipeline.
      // Everything else submits the workflow straight to ComfyUI.
      const useAIPipeline = typeMeta.usesAI && !prompt
      let taskIds: string[]
      let runIds: Array<string | null>
      if (!useAIPipeline) {
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
                const meta = workflowTypeMeta(v)
                setConfig(p => ({ ...p, workflow_type: v, workflow_name: meta.defaultWorkflow }))
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {WORKFLOW_TYPES.map(t => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{typeMeta.hint}</p>
          </div>

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

          {/* Prompt text — goes to the CLIP Text Encode node (image gen / multiangle) */}
          {typeMeta.usesText && (
            <div className="space-y-2">
              <Label>
                Prompt <span className="text-muted-foreground text-xs">(optional)</span>
              </Label>
              <Textarea
                placeholder={
                  typeMeta.usesAI
                    ? 'Leave empty to let the AI write the prompt from the selected image'
                    : 'Edit instruction, e.g. "rotate the camera to a low three-quarter view"'
                }
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                rows={3}
              />
            </div>
          )}

          {/* AI prompt pipeline settings — Image Generation only */}
          {typeMeta.usesAI && (
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

              {/* Vision Model */}
              <div className="space-y-2">
                <Label>Vision Model</Label>
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
          <Button
            onClick={() => processMutation.mutate()}
            disabled={effectivePaths.length === 0 || processMutation.isPending}
            isLoading={processMutation.isPending}
          >
            <Play className="w-4 h-4 mr-2" />
            Process {effectivePaths.length > 0 ? `(${effectivePaths.length})` : ''}
          </Button>
        </div>

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
      </div>
    </div>
  )
}
