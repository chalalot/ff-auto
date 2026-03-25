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
import { Play, RefreshCw, CheckSquare, Square, Loader2, Image as ImageIcon, Clock, Zap, Upload } from 'lucide-react'
import type { ProcessImageConfig, TaskStatusResponse } from '@/types'

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
  const [selectedImages, setSelectedImages] = useState<Set<string>>(new Set())
  const [config, setConfig] = useState<Omit<ProcessImageConfig, 'image_path'>>(DEFAULT_CONFIG)
  const [activeTaskIds, setActiveTaskIds] = useState<string[]>([])

  // Fetch data
  const { data: inputImages = [], isLoading: imagesLoading, refetch: refetchImages } =
    useQuery({ queryKey: ['workspace', 'input-images'], queryFn: workspaceApi.getInputImages })

  const { data: personas = [] } = usePersonas()
  const { data: visionModels = [] } = useVisionModels()
  const { data: clipModels = [] } = useClipModels()
  const { data: loraOptions = [] } = useLoraOptions()
  const { data: lastUsed } = useLastUsed()
  const { data: executions = [] } = useQuery({
    queryKey: ['workspace', 'executions'],
    queryFn: () => workspaceApi.getExecutions({ limit: 20 }),
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

  // Process mutation
  const processMutation = useMutation({
    mutationFn: async () => {
      const paths = Array.from(selectedImages)
      if (paths.length === 1) {
        const result = await workspaceApi.process({ ...config, image_path: paths[0] })
        return [result.task_id]
      } else {
        const result = await workspaceApi.processBatch(paths, config)
        return result.task_ids
      }
    },
    onSuccess: async (taskIds) => {
      setActiveTaskIds(prev => [...prev, ...taskIds])
      // Save last used config
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
    },
  })

  const [uploading, setUploading] = useState(false)

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      const form = new FormData()
      Array.from(files).forEach(f => form.append('files', f))
      await fetch('/api/workspace/upload', { method: 'POST', body: form })
      refetchImages()
    } finally {
      setUploading(false)
    }
  }

  const toggleImage = (path: string) => {
    setSelectedImages(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const selectAll = () => setSelectedImages(new Set(inputImages.map(i => i.path)))
  const clearSelection = () => setSelectedImages(new Set())

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
            {selectedImages.size > 0 && (
              <Badge variant="secondary">{selectedImages.size} selected</Badge>
            )}
            <Button
              onClick={() => processMutation.mutate()}
              disabled={selectedImages.size === 0 || processMutation.isPending}
              isLoading={processMutation.isPending}
            >
              <Play className="w-4 h-4 mr-2" />
              Process {selectedImages.size > 0 ? `(${selectedImages.size})` : ''}
            </Button>
          </div>
        </div>

        <Tabs defaultValue="queue" className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="mx-4 mt-4 w-fit">
            <TabsTrigger value="queue">Input Queue ({inputImages.length})</TabsTrigger>
            <TabsTrigger value="history">Execution History</TabsTrigger>
            <TabsTrigger value="tasks">Active Tasks ({activeTaskIds.length})</TabsTrigger>
          </TabsList>

          {/* Input Queue Tab */}
          <TabsContent value="queue" className="flex-1 overflow-auto px-4 pb-4">
            {/* Upload zone */}
            <label
              className="flex flex-col items-center justify-center w-full mb-4 p-6 border-2 border-dashed border-muted-foreground/30 rounded-lg cursor-pointer hover:border-primary/50 hover:bg-muted/30 transition-colors"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); void handleUpload(e.dataTransfer.files) }}
            >
              <input
                type="file"
                className="hidden"
                accept=".png,.jpg,.jpeg,.webp"
                multiple
                onChange={(e) => void handleUpload(e.target.files)}
              />
              {uploading ? (
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground mb-2" />
              ) : (
                <Upload className="w-6 h-6 text-muted-foreground mb-2" />
              )}
              <p className="text-sm text-muted-foreground">
                {uploading ? 'Uploading...' : 'Drop reference images here or click to upload'}
              </p>
              <p className="text-xs text-muted-foreground/60 mt-1">PNG, JPG, JPEG, WEBP</p>
            </label>

            <div className="flex items-center gap-2 mb-4">
              <Button variant="outline" size="sm" onClick={selectAll}>
                <CheckSquare className="w-4 h-4 mr-2" />Select All
              </Button>
              <Button variant="outline" size="sm" onClick={clearSelection}>
                <Square className="w-4 h-4 mr-2" />Clear
              </Button>
              <Button variant="outline" size="sm" onClick={() => refetchImages()}>
                <RefreshCw className="w-4 h-4 mr-2" />Refresh
              </Button>
            </div>

            {imagesLoading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
              </div>
            ) : inputImages.length === 0 ? (
              <div className="text-center py-16 text-muted-foreground">
                <ImageIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>No images in input directory</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                {inputImages.map(img => (
                  <div
                    key={img.filename}
                    className={`relative rounded-lg border-2 cursor-pointer overflow-hidden transition-all
                      ${selectedImages.has(img.path) ? 'border-primary shadow-md' : 'border-transparent hover:border-muted-foreground/30'}`}
                    onClick={() => toggleImage(img.path)}
                  >
                    <div className="aspect-square bg-muted">
                      <img
                        src={`/api/workspace/input-images/${encodeURIComponent(img.filename)}/thumbnail`}
                        alt={img.filename}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                    </div>
                    <div className="p-2">
                      <p className="text-xs truncate font-medium">{img.filename}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatDistanceToNow(new Date(img.modified_at), { addSuffix: true })}
                      </p>
                    </div>
                    {selectedImages.has(img.path) && (
                      <div className="absolute top-2 right-2 w-5 h-5 bg-primary rounded-full flex items-center justify-center">
                        <CheckSquare className="w-3 h-3 text-primary-foreground" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
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
                  <Card key={exec.execution_id}>
                    <CardContent className="p-3 flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{exec.execution_id}</p>
                        <p className="text-xs text-muted-foreground">
                          {exec.persona} • {formatDistanceToNow(new Date(exec.created_at), { addSuffix: true })}
                        </p>
                      </div>
                      <Badge variant={
                        exec.status === 'completed' ? 'success' :
                        exec.status === 'failed' ? 'destructive' : 'secondary'
                      }>
                        {exec.status}
                      </Badge>
                    </CardContent>
                  </Card>
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
                  <TaskCard key={taskId} taskId={taskId} onDone={() => {
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

// Task progress card component
const TaskCard: React.FC<{ taskId: string; onDone: () => void }> = ({ taskId, onDone }) => {
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

  return (
    <TaskCardDisplay task={task} taskId={taskId} />
  )
}

const TaskCardDisplay: React.FC<{ task: TaskStatusResponse; taskId: string }> = ({ task, taskId }) => {
  return (
    <Card className={task.state === 'FAILURE' ? 'border-destructive' : task.state === 'SUCCESS' ? 'border-success' : ''}>
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-muted-foreground truncate">{taskId}</span>
          <Badge variant={
            task.state === 'SUCCESS' ? 'success' :
            task.state === 'FAILURE' ? 'destructive' :
            'secondary'
          }>
            {task.state}
          </Badge>
        </div>
        <p className="text-sm">{task.status_message}</p>
        {task.progress !== undefined && task.progress > 0 && (
          <div className="space-y-1">
            <Progress value={task.progress} className="h-2" />
            <p className="text-xs text-right text-muted-foreground">{Math.round(task.progress)}%</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
