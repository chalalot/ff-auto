import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'
import { pipelineApi } from '@/api/pipeline'
import { configApi } from '@/api/config'
import { usePersonas, useVisionModels, useLoraOptions, useLastUsed } from '@/hooks/usePersonas'
import { useTaskProgress } from '@/hooks/useTaskProgress'
import { useActiveTasks } from '@/hooks/useActiveTasks'
import { useProjectId } from '@/hooks/useProjectId'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { formatDistanceToNow } from 'date-fns'
import { Play, Loader2, Image as ImageIcon, Clock, Zap, Upload, Info, X, FileText, ExternalLink } from 'lucide-react'
import { Textarea } from '@/components/ui/textarea'
import { WorkflowParametersPanel } from '@/components/workspace/WorkflowParametersPanel'
import { ImageLibrary } from '@/components/workspace/ImageLibrary'
import { CaptionExportTab } from '@/components/workspace/CaptionExportTab'
import { ReviewQueueSection } from '@/components/review/ReviewQueueSection'
import { resolveDroppedFiles, uploadErrorMessage } from '@/lib/uploads'
import type { ProcessImageConfig, ExecutionRecord, ActiveTask, WorkflowParameters } from '@/types'
import type { PipelineRunSummary } from '@/types/pipeline'

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

// Default config
const DEFAULT_CONFIG: Omit<ProcessImageConfig, 'image_path'> = {
  persona: '',
  workflow_type: 'image_generation',
  vision_model: 'gpt-4o',
  variation_count: 1,
  workflow_name: '',
}

export const WorkspacePage: React.FC = () => {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
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

  const { data: activeTasks = [] } = useActiveTasks()

  const { data: personas = [] } = usePersonas()
  const { data: visionModels = [] } = useVisionModels()
  const { data: loraOptions = [] } = useLoraOptions()
  const { data: lastUsed, isSuccess: lastUsedLoaded } = useLastUsed()
  const { data: executions = [] } = useQuery({
    queryKey: ['workspace', 'executions', projectId ?? 'all'],
    queryFn: () => workspaceApi.getExecutions({ limit: 20, project_id: projectId }),
  })
  const { data: pipelineRuns = [], isLoading: pipelineRunsLoading } = useQuery<PipelineRunSummary[]>({
    queryKey: ['pipeline-runs', projectId ?? 'all'],
    queryFn: () => pipelineApi.listRuns({ limit: 20, project_id: projectId }),
    // Fast only while a run is in flight; slow refresh keeps the list current
    // when runs are started elsewhere (other tabs/users).
    refetchInterval: query =>
      (query.state.data ?? []).some(r => r.status === 'queued' || r.status === 'running')
        ? 5000
        : 30000,
  })

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
      return { taskIds, runIds, paths, configSnapshot: { ...config } }
    },
    onSuccess: async ({ taskIds, runIds }) => {
      // Immediately refresh the global active-tasks list so this session and
      // all other open sessions see the new tasks right away.
      queryClient.invalidateQueries({ queryKey: ['workspace', 'active-tasks'] })
      queryClient.invalidateQueries({ queryKey: ['workspace', 'executions'] })
      queryClient.invalidateQueries({ queryKey: ['pipeline-runs'] })
      queryClient.invalidateQueries({ queryKey: ['workspace', 'ref-images'] })
      if (taskIds.length === 1 && runIds[0]) {
        navigate(`/pipeline-runs/${runIds[0]}`)
      }
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
    <div className="flex h-full">
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

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <h1 className="text-xl font-bold">Workspace</h1>
          <div className="flex items-center gap-2">
            {/* Dispatch failures used to be silent — a batch that 500s just
                stopped spinning, which read as "multi-select doesn't work". */}
            {processMutation.isError && (
              <span
                className="text-xs text-destructive max-w-xs truncate"
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
        </div>

        <Tabs defaultValue="library" className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="mx-4 mt-4 w-fit">
            <TabsTrigger value="library">Library ({library.length})</TabsTrigger>
            <TabsTrigger value="review">Review</TabsTrigger>
            <TabsTrigger value="history">Execution History</TabsTrigger>
            <TabsTrigger value="tasks">Active Tasks ({activeTasks.length})</TabsTrigger>
            <TabsTrigger value="caption-export">Caption Export</TabsTrigger>
          </TabsList>

          {/* Unified Library Tab */}
          <TabsContent value="library" className="flex-1 overflow-auto px-4 pb-4">
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
          </TabsContent>

          {/* Review Queue Tab */}
          <TabsContent value="review" className="flex-1 overflow-auto px-4 pb-4">
            <ReviewQueueSection />
          </TabsContent>

          {/* Execution History Tab */}
          <TabsContent value="history" className="flex-1 overflow-auto px-4 pb-4">
            <div className="space-y-6">
              <section className="space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold">Pipeline Runs</h2>
                    <p className="text-xs text-muted-foreground">Reopen a run to inspect every agent prompt, context, and output.</p>
                  </div>
                  {pipelineRunsLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                </div>
                {pipelineRuns.length === 0 && !pipelineRunsLoading ? (
                  <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">No pipeline runs yet.</div>
                ) : (
                  pipelineRuns.map(run => <PipelineRunHistoryCard key={run.id} run={run} />)
                )}
              </section>

              <section className="space-y-2">
                <h2 className="text-sm font-semibold">Legacy Executions</h2>
              {executions.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground">
                  <Clock className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>No executions yet</p>
                </div>
              ) : (
                executions.map(exec => (
                  <ExecutionCard key={exec.execution_id} exec={exec} />
                ))
              )}
              </section>
            </div>
          </TabsContent>

          {/* Active Tasks Tab — shows all running tasks for all users */}
          <TabsContent value="tasks" className="flex-1 overflow-auto px-4 pb-4">
            <div className="space-y-3">
              {activeTasks.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground">
                  <Zap className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>No active tasks</p>
                  <p className="text-xs mt-1">Refreshes every 5 seconds</p>
                </div>
              ) : (
                activeTasks.map(task => (
                  <GlobalTaskCard key={task.task_id} task={task} />
                ))
              )}
            </div>
          </TabsContent>

          {/* Caption Export Tab */}
          <TabsContent value="caption-export" className="flex-1 overflow-auto px-4 pb-4">
            <CaptionExportTab personas={personas} visionModels={visionModels} defaultConfig={config} activeTasks={activeTasks} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// Unified image library component
// ------------------------------------------------------------------
// ------------------------------------------------------------------
// ------------------------------------------------------------------
// Shared helpers
// ------------------------------------------------------------------
function refFilenameFromPath(refPath?: string): string | null {
  if (!refPath) return null
  return refPath.split('/').pop() ?? null
}

function formatPipelineName(name: string) {
  return name.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase())
}

const InfoModal: React.FC<{ title: string; onClose: () => void; children: React.ReactNode }> = ({ title, onClose, children }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
    <div
      className="bg-card border rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col"
      onClick={e => e.stopPropagation()}
    >
      <div className="flex items-center justify-between p-4 border-b shrink-0">
        <h3 className="font-semibold text-sm">{title}</h3>
        <button className="text-muted-foreground hover:text-foreground transition-colors" onClick={onClose}>
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="overflow-y-auto p-4 space-y-3 text-sm">{children}</div>
    </div>
  </div>
)

// ------------------------------------------------------------------
// Global task card — shows a task from the shared Redis registry.
// Adds live 1s polling on top of the 5s global refresh.
// ------------------------------------------------------------------
const GlobalTaskCard: React.FC<{ task: ActiveTask }> = ({ task }) => {
  const { data: live } = useTaskProgress(task.task_id)

  const state = live?.state ?? task.state
  const statusMessage = live?.status_message ?? task.status_message
  const progress = live?.progress ?? task.progress
  const isCaptionExport = task.task_type === 'caption_export'
  const refFilename = isCaptionExport ? null : refFilenameFromPath(task.image_path)

  return (
    <Card className={state === 'FAILURE' ? 'border-destructive' : state === 'SUCCESS' ? 'border-green-500' : ''}>
      <CardContent className="p-3 flex gap-3">
        {refFilename ? (
          <div className="shrink-0 w-12 h-12 rounded-md overflow-hidden bg-muted border">
            <img
              src={workspaceApi.getRefImageThumbnailUrl(refFilename)}
              alt="ref"
              className="w-full h-full object-cover"
            />
          </div>
        ) : isCaptionExport ? (
          <div className="shrink-0 w-12 h-12 rounded-md bg-muted border flex items-center justify-center">
            <FileText className="w-5 h-5 text-muted-foreground/60" />
          </div>
        ) : null}
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-xs text-muted-foreground truncate">{task.task_id}</span>
            <div className="flex items-center gap-1 shrink-0">
              {isCaptionExport && (
                <Badge variant="outline" className="text-xs">caption export</Badge>
              )}
              {task.persona && (
                <Badge variant="outline" className="text-xs">{task.persona}</Badge>
              )}
              <Badge variant={
                state === 'SUCCESS' ? 'success' :
                state === 'FAILURE' ? 'destructive' :
                'secondary'
              }>
                {state}
              </Badge>
            </div>
          </div>
          {isCaptionExport && task.image_count != null && (
            <p className="text-xs text-muted-foreground">{task.image_count} images</p>
          )}
          <p className="text-sm">{statusMessage}</p>
          {task.run_id && !isCaptionExport && (
            <Link
              to={`/pipeline-runs/${task.run_id}`}
              className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:underline"
            >
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
              Open run trace
            </Link>
          )}
          {progress > 0 && (
            <div className="space-y-1">
              <Progress value={progress} className="h-2" />
              <p className="text-xs text-right text-muted-foreground">{Math.round(progress)}%</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ------------------------------------------------------------------
// Caption Export Tab
// ------------------------------------------------------------------


const PipelineRunHistoryCard: React.FC<{ run: PipelineRunSummary }> = ({ run }) => {
  const input = run.input_payload && typeof run.input_payload === 'object'
    ? run.input_payload as Record<string, unknown>
    : null
  const refFilename = refFilenameFromPath(typeof input?.image_path === 'string' ? input.image_path : undefined)
  const status: 'success' | 'destructive' | 'secondary' = run.status === 'succeeded' ? 'success' : run.status === 'failed' ? 'destructive' : 'secondary'

  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-3">
        {refFilename ? (
          <div className="h-10 w-10 shrink-0 overflow-hidden rounded-md border bg-muted">
            <img
              src={workspaceApi.getRefImageThumbnailUrl(refFilename)}
              alt="ref"
              className="h-full w-full object-cover"
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
            />
          </div>
        ) : (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <Zap className="h-4 w-4 text-muted-foreground/50" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-medium">{formatPipelineName(run.pipeline_name)}</p>
            <Badge variant={status}>{run.status}</Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {refFilename ?? 'No reference image'} - {run.created_at ? formatDistanceToNow(new Date(run.created_at), { addSuffix: true }) : 'Queued'}
          </p>
        </div>
        <Link
          to={`/pipeline-runs/${run.id}`}
          className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-blue-700 hover:underline"
        >
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
          Open trace
        </Link>
      </CardContent>
    </Card>
  )
}

const ExecutionCard: React.FC<{ exec: ExecutionRecord }> = ({ exec }) => {
  const [showInfo, setShowInfo] = useState(false)
  const refFilename = refFilenameFromPath(exec.image_ref_path)

  return (
    <>
      <Card>
        <CardContent className="p-3 flex gap-3 items-start">
          {/* Ref image thumbnail */}
          {refFilename ? (
            <div className="shrink-0 w-12 h-12 rounded-md overflow-hidden bg-muted border">
              <img
                src={workspaceApi.getRefImageThumbnailUrl(refFilename)}
                alt="ref"
                className="w-full h-full object-cover"
                onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
              />
            </div>
          ) : (
            <div className="shrink-0 w-12 h-12 rounded-md bg-muted border flex items-center justify-center">
              <ImageIcon className="w-4 h-4 text-muted-foreground/40" />
            </div>
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium truncate">{exec.execution_id}</p>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                  onClick={() => setShowInfo(true)}
                  title="Show execution info"
                >
                  <Info className="w-3.5 h-3.5" />
                </button>
                <Badge variant={
                  exec.status === 'completed' ? 'success' :
                  exec.status === 'failed' ? 'destructive' : 'secondary'
                }>
                  {exec.status}
                </Badge>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {exec.persona} • {formatDistanceToNow(new Date(exec.created_at), { addSuffix: true })}
            </p>
          </div>
        </CardContent>
      </Card>

      {showInfo && (
        <InfoModal title="Execution info" onClose={() => setShowInfo(false)}>
          {exec.prompt ? (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Prompt sent to ComfyUI</p>
              <pre className="text-xs bg-muted rounded-lg p-3 whitespace-pre-wrap break-words font-mono leading-relaxed">
                {exec.prompt}
              </pre>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No prompt recorded.</p>
          )}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs border-t pt-3">
            {[
              ['Persona', exec.persona ?? '—'],
              ['Status', exec.status],
              ['Created', new Date(exec.created_at).toLocaleString()],
            ].map(([k, v]) => (
              <React.Fragment key={k}>
                <span className="text-muted-foreground">{k}</span>
                <span className="font-medium">{v}</span>
              </React.Fragment>
            ))}
          </div>
          {exec.image_ref_path && (
            <div className="border-t pt-3">
              <p className="text-xs text-muted-foreground mb-1">Ref image path</p>
              <p className="text-xs font-mono break-all">{exec.image_ref_path}</p>
            </div>
          )}
        </InfoModal>
      )}
    </>
  )
}
