import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'
import { configApi } from '@/api/config'
import { usePersonas, useVisionModels, useClipModels, useLoraOptions, useLastUsed } from '@/hooks/usePersonas'
import { useTaskProgress } from '@/hooks/useTaskProgress'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { formatDistanceToNow } from 'date-fns'
import { Play, RefreshCw, CheckSquare, Square, Loader2, Image as ImageIcon, Clock, Zap, Upload, Trash2, Info, X } from 'lucide-react'
import type { ProcessImageConfig, TaskStatusResponse, RefImage, ExecutionRecord } from '@/types'

// Default config
const DEFAULT_CONFIG: Omit<ProcessImageConfig, 'image_path'> = {
  persona: '',
  workflow_type: 'turbo',
  vision_model: 'gpt-4o',
  variation_count: 1,
  strength: 0.8,
  seed_strategy: 'random',
  base_seed: 0,
  width: 1024,
  height: 1600,
  lora_name: '',
  clip_model_type: 'sd3',
}

export const WorkspacePage: React.FC = () => {
  const queryClient = useQueryClient()
  // Unified library selection — all images live in processed/
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set())
  const [config, setConfig] = useState<Omit<ProcessImageConfig, 'image_path'>>(DEFAULT_CONFIG)
  const [activeTaskIds, setActiveTaskIds] = useState<string[]>([])
  // Metadata captured at dispatch time so cards can show ref thumbnail + config info
  const [taskMeta, setTaskMeta] = useState<Record<string, { refImagePath?: string; persona: string; config: Omit<ProcessImageConfig, 'image_path'> }>>({})

  const { data: personas = [] } = usePersonas()
  const { data: visionModels = [] } = useVisionModels()
  const { data: clipModels = [] } = useClipModels()
  const { data: loraOptions = [] } = useLoraOptions()
  const { data: lastUsed } = useLastUsed()
  const { data: executions = [] } = useQuery({
    queryKey: ['workspace', 'executions'],
    queryFn: () => workspaceApi.getExecutions({ limit: 20 }),
  })

  const { data: library = [], refetch: refetchLibrary } = useQuery({
    queryKey: ['workspace', 'ref-images'],
    queryFn: workspaceApi.getRefImages,
  })

  // Load last used config on mount
  React.useEffect(() => {
    if (lastUsed) {
      setConfig(prev => ({
        ...prev,
        persona: lastUsed.persona || prev.persona,
        vision_model: lastUsed.vision_model || prev.vision_model,
        clip_model_type: lastUsed.clip_model_type || prev.clip_model_type,
        variation_count: lastUsed.variations || prev.variation_count,
        strength: lastUsed.strength || prev.strength,
        lora_name: lastUsed.lora_name || prev.lora_name,
        width: lastUsed.width || prev.width,
        height: lastUsed.height || prev.height,
        seed_strategy: lastUsed.seed_strategy || prev.seed_strategy,
        base_seed: lastUsed.base_seed || prev.base_seed,
        workflow_type: lastUsed.workflow_type || prev.workflow_type,
      }))
    }
  }, [lastUsed])

  // Set first persona as default
  React.useEffect(() => {
    if (personas.length > 0 && !config.persona) {
      setConfig(prev => ({ ...prev, persona: personas[0].name }))
    }
  }, [personas, config.persona])

  // All images live in processed/ — always skip prepare
  const processMutation = useMutation({
    mutationFn: async () => {
      const paths = Array.from(selectedPaths)
      let taskIds: string[]
      if (paths.length === 1) {
        const result = await workspaceApi.process({ ...config, image_path: paths[0], skip_prepare: true })
        taskIds = [result.task_id]
      } else {
        const result = await workspaceApi.processBatch(paths, { ...config, skip_prepare: true })
        taskIds = result.task_ids
      }
      return { taskIds, paths, configSnapshot: { ...config } }
    },
    onSuccess: async ({ taskIds, paths, configSnapshot }) => {
      setActiveTaskIds(prev => [...prev, ...taskIds])
      setTaskMeta(prev => {
        const next = { ...prev }
        taskIds.forEach((id, i) => {
          next[id] = { refImagePath: paths[i], persona: configSnapshot.persona, config: configSnapshot }
        })
        return next
      })
      await configApi.saveLastUsed({
        persona: config.persona,
        vision_model: config.vision_model,
        clip_model_type: config.clip_model_type,
        variations: config.variation_count,
        strength: config.strength,
        lora_name: config.lora_name,
        width: config.width,
        height: config.height,
        seed_strategy: config.seed_strategy,
        base_seed: config.base_seed,
        workflow_type: config.workflow_type,
      })
      queryClient.invalidateQueries({ queryKey: ['workspace', 'executions'] })
      queryClient.invalidateQueries({ queryKey: ['workspace', 'ref-images'] })
    },
  })

  const [uploading, setUploading] = useState(false)
  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      await workspaceApi.uploadRefImages(Array.from(files))
      queryClient.invalidateQueries({ queryKey: ['workspace', 'ref-images'] })
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

  const selectAll = () => setSelectedPaths(new Set(library.map(i => i.path)))
  const clearSelection = () => setSelectedPaths(new Set())

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

          {/* Workflow Type */}
          <div className="space-y-2">
            <Label>Workflow Type</Label>
            <Select value={config.workflow_type} onValueChange={(v) => setConfig(p => ({ ...p, workflow_type: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="turbo">Turbo</SelectItem>
                <SelectItem value="standard">Standard</SelectItem>
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

          {/* CLIP Model */}
          <div className="space-y-2">
            <Label>CLIP Model</Label>
            <Select value={config.clip_model_type} onValueChange={(v) => setConfig(p => ({ ...p, clip_model_type: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {clipModels.map(m => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Separator />

          {/* Variations */}
          <div className="space-y-2">
            <Label>Variations: {config.variation_count}</Label>
            <Slider
              min={1} max={5} step={1}
              value={[config.variation_count]}
              onValueChange={([v]) => setConfig(p => ({ ...p, variation_count: v }))}
            />
          </div>

          {/* Strength */}
          <div className="space-y-2">
            <Label>Strength: {config.strength.toFixed(2)}</Label>
            <Slider
              min={0} max={2} step={0.05}
              value={[config.strength]}
              onValueChange={([v]) => setConfig(p => ({ ...p, strength: v }))}
            />
          </div>

          <Separator />

          {/* Dimensions */}
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Width</Label>
              <Input
                type="number" value={config.width}
                onChange={(e) => setConfig(p => ({ ...p, width: parseInt(e.target.value) || p.width }))}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Height</Label>
              <Input
                type="number" value={config.height}
                onChange={(e) => setConfig(p => ({ ...p, height: parseInt(e.target.value) || p.height }))}
              />
            </div>
          </div>

          {/* Seed Strategy */}
          <div className="space-y-2">
            <Label>Seed Strategy</Label>
            <Select value={config.seed_strategy} onValueChange={(v) => setConfig(p => ({ ...p, seed_strategy: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="random">Random</SelectItem>
                <SelectItem value="fixed">Fixed</SelectItem>
              </SelectContent>
            </Select>
            {config.seed_strategy === 'fixed' && (
              <Input
                type="number"
                placeholder="Base seed"
                value={config.base_seed}
                onChange={(e) => setConfig(p => ({ ...p, base_seed: parseInt(e.target.value) || 0 }))}
              />
            )}
          </div>

          {/* LoRA */}
          <div className="space-y-2">
            <Label>LoRA</Label>
            <Select value={config.lora_name} onValueChange={(v) => setConfig(p => ({ ...p, lora_name: v }))}>
              <SelectTrigger><SelectValue placeholder="Select LoRA" /></SelectTrigger>
              <SelectContent>
                {loraOptions.map(l => (
                  <SelectItem key={l} value={l}>{l}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <h1 className="text-xl font-bold">Workspace</h1>
          <div className="flex items-center gap-2">
            {selectedPaths.size > 0 && (
              <Badge variant="secondary">{selectedPaths.size} selected</Badge>
            )}
            <Button
              onClick={() => processMutation.mutate()}
              disabled={selectedPaths.size === 0 || processMutation.isPending}
              isLoading={processMutation.isPending}
            >
              <Play className="w-4 h-4 mr-2" />
              Process {selectedPaths.size > 0 ? `(${selectedPaths.size})` : ''}
            </Button>
          </div>
        </div>

        <Tabs defaultValue="library" className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="mx-4 mt-4 w-fit">
            <TabsTrigger value="library">Library ({library.length})</TabsTrigger>
            <TabsTrigger value="history">Execution History</TabsTrigger>
            <TabsTrigger value="tasks">Active Tasks ({activeTaskIds.length})</TabsTrigger>
          </TabsList>

          {/* Unified Library Tab */}
          <TabsContent value="library" className="flex-1 overflow-auto px-4 pb-4">
            {/* Upload zone */}
            <label
              className="flex flex-col items-center justify-center w-full mb-4 p-6 border-2 border-dashed border-muted-foreground/30 rounded-lg cursor-pointer hover:border-primary/50 hover:bg-muted/30 transition-colors"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); void handleUpload(e.dataTransfer.files) }}
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
            </label>

            <div className="flex items-center gap-2 mb-3">
              <Button variant="outline" size="sm" onClick={selectAll}>
                <CheckSquare className="w-4 h-4 mr-2" />Select All
              </Button>
              <Button variant="outline" size="sm" onClick={clearSelection}>
                <Square className="w-4 h-4 mr-2" />Clear
              </Button>
              <Button variant="outline" size="sm" onClick={() => refetchLibrary()}>
                <RefreshCw className="w-4 h-4 mr-2" />Refresh
              </Button>
            </div>

            <ImageLibrary
              images={library}
              selectedPaths={selectedPaths}
              onToggle={toggleImage}
              onDelete={(filename) => deleteMutation.mutate(filename)}
              deletingFilename={deleteMutation.isPending ? (deleteMutation.variables as string) : null}
            />
          </TabsContent>

          {/* Execution History Tab */}
          <TabsContent value="history" className="flex-1 overflow-auto px-4 pb-4">
            <div className="space-y-2">
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
            </div>
          </TabsContent>

          {/* Active Tasks Tab */}
          <TabsContent value="tasks" className="flex-1 overflow-auto px-4 pb-4">
            <div className="space-y-3">
              {activeTaskIds.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground">
                  <Zap className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>No active tasks</p>
                </div>
              ) : (
                activeTaskIds.map(taskId => (
                  <TaskCard key={taskId} taskId={taskId} meta={taskMeta[taskId]} onDone={() => {
                    setActiveTaskIds(prev => prev.filter(id => id !== taskId))
                    queryClient.invalidateQueries({ queryKey: ['workspace', 'executions'] })
                  }} />
                ))
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// Unified image library component
// ------------------------------------------------------------------
const ImageLibrary: React.FC<{
  images: RefImage[]
  selectedPaths: Set<string>
  onToggle: (path: string) => void
  onDelete: (filename: string) => void
  deletingFilename: string | null
}> = ({ images, selectedPaths, onToggle, onDelete, deletingFilename }) => {
  const unused = images.filter(i => !i.is_used)
  const used = images.filter(i => i.is_used)

  if (images.length === 0) {
    return (
      <div className="text-center py-16 text-muted-foreground">
        <ImageIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No images yet</p>
        <p className="text-xs mt-1">Upload images above to get started</p>
      </div>
    )
  }

  const renderGrid = (items: RefImage[]) => (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
      {items.map(img => {
        const isSelected = selectedPaths.has(img.path)
        const isDeleting = deletingFilename === img.filename
        return (
          <div
            key={img.filename}
            className={`relative rounded-lg border-2 overflow-hidden transition-all
              ${isSelected ? 'border-amber-500 shadow-md' : 'border-transparent hover:border-muted-foreground/30'}
              ${isDeleting ? 'opacity-40 pointer-events-none' : ''}`}
          >
            <div
              className="aspect-square bg-muted cursor-pointer"
              onClick={() => onToggle(img.path)}
            >
              <img
                src={workspaceApi.getRefImageThumbnailUrl(img.filename)}
                alt={img.filename}
                className="w-full h-full object-cover"
                loading="lazy"
              />
            </div>
            <div className="p-2 flex items-start justify-between gap-1">
              <div className="min-w-0 flex-1 cursor-pointer" onClick={() => onToggle(img.path)}>
                <p className="text-xs truncate font-medium">{img.filename}</p>
                {img.use_count > 0 && (
                  <p className="text-xs text-muted-foreground">{img.use_count}× used</p>
                )}
              </div>
              <button
                className="shrink-0 p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                onClick={(e) => { e.stopPropagation(); onDelete(img.filename) }}
                title="Delete"
              >
                {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              </button>
            </div>
            {isSelected && (
              <div className="absolute top-2 right-2 w-5 h-5 bg-amber-500 rounded-full flex items-center justify-center">
                <CheckSquare className="w-3 h-3 text-white" />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )

  return (
    <div className="space-y-6">
      {unused.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-muted-foreground/40 inline-block" />
            Unused ({unused.length})
          </h3>
          {renderGrid(unused)}
        </div>
      )}
      {used.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
            Used ({used.length})
          </h3>
          {renderGrid(used)}
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------
// Shared helpers
// ------------------------------------------------------------------
function refFilenameFromPath(refPath?: string): string | null {
  if (!refPath) return null
  return refPath.split('/').pop() ?? null
}

// ------------------------------------------------------------------
// Info Modal — lightweight overlay (no Dialog component available)
// ------------------------------------------------------------------
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
// Task progress card component
// ------------------------------------------------------------------
type TaskMeta = { refImagePath?: string; persona: string; config: Omit<ProcessImageConfig, 'image_path'> }

const TaskCard: React.FC<{ taskId: string; meta?: TaskMeta; onDone: () => void }> = ({ taskId, meta, onDone }) => {
  const { data: task } = useTaskProgress(taskId)

  React.useEffect(() => {
    if (task?.state === 'SUCCESS' || task?.state === 'FAILURE') {
      const timer = setTimeout(onDone, 3000)
      return () => clearTimeout(timer)
    }
  }, [task?.state, onDone])

  if (!task) return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="font-mono text-xs">{taskId}</span>
        </div>
      </CardContent>
    </Card>
  )

  return <TaskCardDisplay task={task} taskId={taskId} meta={meta} />
}

const TaskCardDisplay: React.FC<{ task: TaskStatusResponse; taskId: string; meta?: TaskMeta }> = ({ task, taskId, meta }) => {
  const [showInfo, setShowInfo] = useState(false)
  const refFilename = refFilenameFromPath(meta?.refImagePath)

  return (
    <>
      <Card className={task.state === 'FAILURE' ? 'border-destructive' : task.state === 'SUCCESS' ? 'border-success' : ''}>
        <CardContent className="p-3 flex gap-3">
          {/* Ref image thumbnail */}
          {refFilename && (
            <div className="shrink-0 w-12 h-12 rounded-md overflow-hidden bg-muted border">
              <img
                src={workspaceApi.getRefImageThumbnailUrl(refFilename)}
                alt="ref"
                className="w-full h-full object-cover"
              />
            </div>
          )}
          <div className="flex-1 min-w-0 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs text-muted-foreground truncate">{taskId}</span>
              <div className="flex items-center gap-1 shrink-0">
                {meta && (
                  <button
                    className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                    onClick={() => setShowInfo(true)}
                    title="Show dispatch info"
                  >
                    <Info className="w-3.5 h-3.5" />
                  </button>
                )}
                <Badge variant={
                  task.state === 'SUCCESS' ? 'success' :
                  task.state === 'FAILURE' ? 'destructive' :
                  'secondary'
                }>
                  {task.state}
                </Badge>
              </div>
            </div>
            <p className="text-sm">{task.status_message}</p>
            {task.progress !== undefined && task.progress > 0 && (
              <div className="space-y-1">
                <Progress value={task.progress} className="h-2" />
                <p className="text-xs text-right text-muted-foreground">{Math.round(task.progress)}%</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {showInfo && meta && (
        <InfoModal title="Dispatch config" onClose={() => setShowInfo(false)}>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
            {Object.entries({
              Persona: meta.persona,
              Workflow: meta.config.workflow_type,
              'Vision model': meta.config.vision_model,
              'CLIP model': meta.config.clip_model_type,
              Variations: meta.config.variation_count,
              Strength: meta.config.strength,
              'Seed strategy': meta.config.seed_strategy,
              ...(meta.config.seed_strategy === 'fixed' ? { 'Base seed': meta.config.base_seed } : {}),
              Width: meta.config.width,
              Height: meta.config.height,
              LoRA: meta.config.lora_name || '—',
            }).map(([k, v]) => (
              <React.Fragment key={k}>
                <span className="text-muted-foreground">{k}</span>
                <span className="font-medium">{String(v)}</span>
              </React.Fragment>
            ))}
          </div>
          {meta.refImagePath && (
            <div className="mt-3 pt-3 border-t">
              <p className="text-xs text-muted-foreground mb-1">Ref image</p>
              <p className="text-xs font-mono break-all">{meta.refImagePath}</p>
            </div>
          )}
        </InfoModal>
      )}
    </>
  )
}

// ------------------------------------------------------------------
// Execution history card
// ------------------------------------------------------------------
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
