import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'
import { configApi } from '@/api/config'
import { usePersonas, useVisionModels, useClipModels, useLoraOptions, useLastUsed } from '@/hooks/usePersonas'
import { useTaskProgress } from '@/hooks/useTaskProgress'
import { useActiveTasks } from '@/hooks/useActiveTasks'
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
import { formatDistanceToNow, format } from 'date-fns'
import { Play, RefreshCw, CheckSquare, Square, Loader2, Image as ImageIcon, Clock, Zap, Upload, Trash2, Info, X, Download, FileText, HardDrive, CheckCircle2, Cpu, CalendarDays, ChevronLeft, ChevronRight, PenLine, Copy } from 'lucide-react'
import { Textarea } from '@/components/ui/textarea'
import type { ProcessImageConfig, RefImage, ExecutionRecord, ActiveTask, CaptionExportEntry } from '@/types'

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
  const configInitializedRef = React.useRef(false)

  const { data: activeTasks = [] } = useActiveTasks()

  const { data: personas = [] } = usePersonas()
  const { data: visionModels = [] } = useVisionModels()
  const { data: clipModels = [] } = useClipModels()
  const { data: loraOptions = [] } = useLoraOptions()
  const { data: lastUsed, isSuccess: lastUsedLoaded } = useLastUsed()
  const { data: executions = [] } = useQuery({
    queryKey: ['workspace', 'executions'],
    queryFn: () => workspaceApi.getExecutions({ limit: 20 }),
  })

  const { data: library = [], refetch: refetchLibrary } = useQuery({
    queryKey: ['workspace', 'ref-images'],
    queryFn: workspaceApi.getRefImages,
  })

  // Load last used config on mount — runs once when query resolves
  React.useEffect(() => {
    if (!lastUsedLoaded) return
    if (lastUsed) {
      setConfig(prev => ({
        ...prev,
        persona: lastUsed.persona || prev.persona,
        vision_model: lastUsed.vision_model || prev.vision_model,
        clip_model_type: lastUsed.clip_model_type || prev.clip_model_type,
        variation_count: lastUsed.variations ?? prev.variation_count,
        strength: lastUsed.strength ?? prev.strength,
        lora_name: lastUsed.lora_name ?? prev.lora_name,
        width: lastUsed.width || prev.width,
        height: lastUsed.height || prev.height,
        seed_strategy: lastUsed.seed_strategy || prev.seed_strategy,
        base_seed: lastUsed.base_seed ?? prev.base_seed,
        workflow_type: lastUsed.workflow_type || prev.workflow_type,
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
    onSuccess: async () => {
      // Immediately refresh the global active-tasks list so this session and
      // all other open sessions see the new tasks right away.
      queryClient.invalidateQueries({ queryKey: ['workspace', 'active-tasks'] })
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
            <TabsTrigger value="tasks">Active Tasks ({activeTasks.length})</TabsTrigger>
            <TabsTrigger value="caption-export">Caption Export</TabsTrigger>
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
const PER_PAGE = 48

type FilterStatus = 'all' | 'unused' | 'used'
type SortBy = 'newest' | 'oldest' | 'name_asc' | 'name_desc'

const ImageLibrary: React.FC<{
  images: RefImage[]
  selectedPaths: Set<string>
  onToggle: (path: string) => void
  onDelete: (filename: string) => void
  deletingFilename: string | null
  onSelectAll: (paths: string[]) => void
  onClearSelection: () => void
  onRefresh: () => void
}> = ({ images, selectedPaths, onToggle, onDelete, deletingFilename, onSelectAll, onClearSelection, onRefresh }) => {
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all')
  const [sortBy, setSortBy] = useState<SortBy>('newest')
  const [groupByDay, setGroupByDay] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)

  const filtered = React.useMemo(() => {
    if (filterStatus === 'unused') return images.filter(i => !i.is_used)
    if (filterStatus === 'used') return images.filter(i => i.is_used)
    return images
  }, [images, filterStatus])

  const sorted = React.useMemo(() => {
    return [...filtered].sort((a, b) => {
      if (sortBy === 'newest') return b.modified_at - a.modified_at
      if (sortBy === 'oldest') return a.modified_at - b.modified_at
      if (sortBy === 'name_asc') return a.filename.localeCompare(b.filename)
      return b.filename.localeCompare(a.filename)
    })
  }, [filtered, sortBy])

  const totalPages = Math.max(1, Math.ceil(sorted.length / PER_PAGE))
  const safePage = Math.min(currentPage, totalPages)
  const paginated = sorted.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE)

  React.useEffect(() => { setCurrentPage(1) }, [filterStatus, sortBy, images.length])

  const displayGroups = React.useMemo(() => {
    if (!groupByDay) return [{ label: null as string | null, items: paginated }]
    const groups: Record<string, RefImage[]> = {}
    for (const img of paginated) {
      const key = format(new Date(img.modified_at * 1000), 'yyyy-MM-dd')
      if (!groups[key]) groups[key] = []
      groups[key].push(img)
    }
    return Object.entries(groups).map(([key, items]) => ({
      label: format(new Date(key + 'T00:00:00'), 'EEEE, MMMM d, yyyy'),
      items,
    }))
  }, [paginated, groupByDay])

  const unusedCount = images.filter(i => !i.is_used).length
  const usedCount = images.filter(i => i.is_used).length

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
              ${isSelected
                ? 'border-amber-500 shadow-md'
                : img.is_used
                  ? 'border-yellow-500/70 hover:border-yellow-500'
                  : 'border-green-500/70 hover:border-green-500'}
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
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => onSelectAll(sorted.map(i => i.path))}>
          <CheckSquare className="w-4 h-4 mr-1.5" />Select All ({filtered.length})
        </Button>
        <Button variant="outline" size="sm" onClick={onClearSelection}>
          <Square className="w-4 h-4 mr-1.5" />Clear
        </Button>
        <Button variant="outline" size="sm" onClick={onRefresh}>
          <RefreshCw className="w-4 h-4 mr-1.5" />Refresh
        </Button>

        <div className="flex-1" />

        {/* Filter */}
        <Select value={filterStatus} onValueChange={(v) => setFilterStatus(v as FilterStatus)}>
          <SelectTrigger className="h-8 w-[120px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All ({images.length})</SelectItem>
            <SelectItem value="unused">Unused ({unusedCount})</SelectItem>
            <SelectItem value="used">Used ({usedCount})</SelectItem>
          </SelectContent>
        </Select>

        {/* Sort */}
        <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortBy)}>
          <SelectTrigger className="h-8 w-[130px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="newest">Newest first</SelectItem>
            <SelectItem value="oldest">Oldest first</SelectItem>
            <SelectItem value="name_asc">Name A→Z</SelectItem>
            <SelectItem value="name_desc">Name Z→A</SelectItem>
          </SelectContent>
        </Select>

        {/* Group by day toggle */}
        <button
          onClick={() => setGroupByDay(v => !v)}
          className={`flex items-center gap-1.5 h-8 px-2.5 rounded-md text-xs font-medium border transition-colors ${
            groupByDay
              ? 'bg-primary/10 border-primary/30 text-primary'
              : 'bg-background border-border text-muted-foreground hover:text-foreground'
          }`}
          title="Group by day"
        >
          <CalendarDays className="w-3.5 h-3.5" />
          By Day
        </button>
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <ImageIcon className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No images match the current filter</p>
        </div>
      ) : (
        <>
          {/* Summary */}
          <p className="text-xs text-muted-foreground">
            {filtered.length !== images.length
              ? `${filtered.length} of ${images.length} images`
              : `${images.length} images`}
            {totalPages > 1 && ` — page ${safePage} of ${totalPages}`}
          </p>

          {/* Image groups */}
          <div className="space-y-6">
            {displayGroups.map(({ label, items }) => (
              <div key={label ?? 'all'}>
                {label && (
                  <h3 className="text-xs font-medium text-muted-foreground mb-3 flex items-center gap-2">
                    <CalendarDays className="w-3.5 h-3.5" />
                    {label}
                    <span className="opacity-60">({items.length})</span>
                  </h3>
                )}
                {renderGrid(items)}
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2 pb-4">
              <Button
                variant="outline" size="sm"
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={safePage <= 1}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-xs text-muted-foreground min-w-[90px] text-center">
                Page {safePage} of {totalPages}
              </span>
              <Button
                variant="outline" size="sm"
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          )}
        </>
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

interface LoraConfig {
  dataset_source: string
  lora_name: string
  steps: number
  save_every: number
  sample_every: number
  sample_prompts: string  // newline-separated in the textarea
}

interface RunpodJobEntry {
  job_id: string
  endpoint_id: string
  lora_name: string
  submitted_at: string  // ISO string
  job_input: Record<string, unknown>
  status: string | null
  output: Record<string, unknown> | null
}

const DEFAULT_LORA: LoraConfig = {
  dataset_source: '',
  lora_name: '',
  steps: 2000,
  save_every: 500,
  sample_every: 500,
  sample_prompts: '',
}

const CaptionExportTab: React.FC<{
  personas: Array<{ name: string }>
  visionModels: Array<{ value: string; label: string }>
  defaultConfig: Omit<ProcessImageConfig, 'image_path'>
  activeTasks: ActiveTask[]
}> = ({ personas, visionModels, defaultConfig, activeTasks }) => {
  const [entries, setEntries] = useState<CaptionExportEntry[]>(() => {
    try { return JSON.parse(sessionStorage.getItem('ff:ce:entries') ?? 'null') ?? [] } catch { return [] }
  })
  const [persona, setPersona] = useState(defaultConfig.persona)
  const [visionModel, setVisionModel] = useState(defaultConfig.vision_model)
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(null)
  const [taskId, setTaskId] = useState<string | null>(() => {
    try { return sessionStorage.getItem('ff:ce:taskId') } catch { return null }
  })
  const [started, setStarted] = useState(() => {
    try { return sessionStorage.getItem('ff:ce:started') === '1' } catch { return false }
  })

  // Persist session state so navigation away doesn't wipe the run
  React.useEffect(() => {
    try { sessionStorage.setItem('ff:ce:entries', JSON.stringify(entries)) } catch {}
  }, [entries])
  React.useEffect(() => {
    try {
      if (taskId) sessionStorage.setItem('ff:ce:taskId', taskId)
      else sessionStorage.removeItem('ff:ce:taskId')
    } catch {}
  }, [taskId])
  React.useEffect(() => {
    try { sessionStorage.setItem('ff:ce:started', started ? '1' : '0') } catch {}
  }, [started])
  React.useEffect(() => {
    workspaceApi.runpodJobs()
      .then(jobs => setRunpodJobs(jobs))
      .catch(err => console.error('Failed to load RunPod job history:', err))
      .finally(() => setRunpodJobsLoaded(true))
  }, [])

  // Re-attach to a still-running task if session storage didn't have it (e.g. hard refresh)
  const restoredRef = React.useRef(false)
  React.useEffect(() => {
    if (restoredRef.current || started) return
    const running = activeTasks.find(t => t.task_type === 'caption_export')
    if (running) {
      setTaskId(running.task_id)
      setStarted(true)
      restoredRef.current = true
    }
  }, [activeTasks, started])

  // Google Drive state
  const [source, setSource] = useState<'local' | 'drive' | 'manual'>('local')
  const [driveFolderUrl, setDriveFolderUrl] = useState('')
  const [driveMaxDimension, setDriveMaxDimension] = useState(1024)
  const [driveFetching, setDriveFetching] = useState(false)
  const [driveFetchError, setDriveFetchError] = useState<string | null>(null)
  const [driveUploading, setDriveUploading] = useState(false)
  const [driveUploadError, setDriveUploadError] = useState<string | null>(null)
  const [driveUploadResult, setDriveUploadResult] = useState<{ filename: string; fileId: string; publicUrl: string } | null>(null)

  // Manual captions state
  const [manualCaptions, setManualCaptions] = useState<Record<string, string>>({})
  const [manualExporting, setManualExporting] = useState(false)
  const [manualExportResult, setManualExportResult] = useState<{ fileId: string; folderId: string; filename: string; publicUrl: string } | null>(null)
  const [manualExportError, setManualExportError] = useState<string | null>(null)
  const [copiedFolderId, setCopiedFolderId] = useState(false)

  // LoRA / RunPod state
  const [loraConfig, setLoraConfig] = useState<LoraConfig>(DEFAULT_LORA)
  const [runpodJobs, setRunpodJobs] = useState<RunpodJobEntry[]>([])
  const [runpodJobsLoaded, setRunpodJobsLoaded] = useState(false)
  const [runpodSubmitting, setRunpodSubmitting] = useState(false)
  const [checkingJobId, setCheckingJobId] = useState<string | null>(null)

  // Sync persona default once it's loaded
  React.useEffect(() => {
    if (!persona && defaultConfig.persona) setPersona(defaultConfig.persona)
  }, [defaultConfig.persona]) // eslint-disable-line react-hooks/exhaustive-deps

  // Pre-fill dataset_source when Drive upload completes
  React.useEffect(() => {
    if (driveUploadResult?.fileId) {
      setLoraConfig(prev => ({ ...prev, dataset_source: `gdrive://${driveUploadResult.fileId}` }))
    }
  }, [driveUploadResult])

  // Init caption slots as new entries arrive in manual mode
  React.useEffect(() => {
    if (source !== 'manual') return
    setManualCaptions(prev => {
      const next = { ...prev }
      entries.forEach(e => { if (!(e.stem in next)) next[e.stem] = '' })
      return next
    })
  }, [entries, source])

  const { data: task } = useTaskProgress(started ? taskId : null)
  const isDone = task?.state === 'SUCCESS' || task?.state === 'FAILURE'

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0 || uploadProgress !== null) return
    const arr = Array.from(files)
    setUploadProgress({ current: 0, total: arr.length })
    for (let i = 0; i < arr.length; i++) {
      try {
        const res = await workspaceApi.captionExportUploadOne(arr[i])
        setEntries(prev => [...prev, ...res.entries])
      } catch {
        // skip failed file, continue with rest
      }
      setUploadProgress({ current: i + 1, total: arr.length })
    }
    setUploadProgress(null)
  }

  const handleDriveFetch = async () => {
    if (!driveFolderUrl.trim()) return
    setDriveFetching(true)
    setDriveFetchError(null)
    setEntries([])
    try {
      const res = await workspaceApi.captionExportGdriveFetch({
        folder_url: driveFolderUrl.trim(),
        max_dimension: driveMaxDimension,
      })
      setEntries(res.entries)
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err instanceof Error ? err.message : 'Failed to fetch from Drive')
      setDriveFetchError(detail)
    } finally {
      setDriveFetching(false)
    }
  }

  const handleDriveUpload = async () => {
    if (!taskId) return
    setDriveUploading(true)
    setDriveUploadError(null)
    try {
      const res = await workspaceApi.captionExportGdriveUploadZip(taskId)
      setDriveUploadResult({ filename: res.filename, fileId: res.file_id, publicUrl: res.public_url })
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err instanceof Error ? err.message : 'Failed to upload to Drive')
      setDriveUploadError(detail)
    } finally {
      setDriveUploading(false)
    }
  }

  const handleRunpodSubmit = async () => {
    if (!loraConfig.dataset_source || !loraConfig.lora_name) return
    setRunpodSubmitting(true)
    const job_input = {
      ...loraConfig,
      sample_prompts: loraConfig.sample_prompts
        .split('\n')
        .map(s => s.trim())
        .filter(Boolean),
    }
    try {
      const res = await workspaceApi.runpodSubmit({ job_input })
      setRunpodJobs(prev => [{
        job_id: res.job_id,
        endpoint_id: res.endpoint_id,
        lora_name: loraConfig.lora_name,
        submitted_at: new Date().toISOString(),
        job_input: job_input as Record<string, unknown>,
        status: null,
        output: null,
      }, ...prev])
    } finally {
      setRunpodSubmitting(false)
    }
  }

  const handleRunpodCheckStatus = async (jobId: string, endpointId: string) => {
    setCheckingJobId(jobId)
    try {
      const data = await workspaceApi.runpodStatus(jobId, endpointId)
      setRunpodJobs(prev => prev.map(j =>
        j.job_id === jobId
          ? { ...j, status: data.status ?? null, output: (data.output as Record<string, unknown> | null | undefined) ?? null }
          : j
      ))
    } finally {
      setCheckingJobId(null)
    }
  }

  const handleManualExport = async () => {
    if (entries.length === 0) return
    setManualExporting(true)
    setManualExportError(null)
    try {
      const res = await workspaceApi.captionExportManualToDrive({ entries, captions: manualCaptions })
      setManualExportResult({ fileId: res.file_id, folderId: res.folder_id, filename: res.filename, publicUrl: res.public_url })
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err instanceof Error ? err.message : 'Export failed')
      setManualExportError(detail)
    } finally {
      setManualExporting(false)
    }
  }

  const handleCopyFolderId = async (id: string) => {
    await navigator.clipboard.writeText(id)
    setCopiedFolderId(true)
    setTimeout(() => setCopiedFolderId(false), 1500)
  }

  const handleRemove = (stem: string) => {
    setEntries(prev => prev.filter(e => e.stem !== stem))
  }

  const handleStart = async () => {
    if (entries.length === 0 || !persona) return
    const res = await workspaceApi.captionExportStart({
      image_entries: entries,
      persona,
      vision_model: visionModel,
      workflow_type: 'turbo',
    })
    setTaskId(res.task_id)
    setStarted(true)
  }

  const handleDownload = () => {
    if (!taskId) return
    const url = workspaceApi.getCaptionExportDownloadUrl(taskId)
    const a = document.createElement('a')
    a.href = url
    a.download = `caption_export_${taskId.slice(0, 8)}.zip`
    a.click()
  }

  const handleReset = () => {
    setEntries([])
    setTaskId(null)
    setStarted(false)
    setDriveUploadResult(null)
    setLoraConfig(DEFAULT_LORA)
    setManualCaptions({})
    setManualExportResult(null)
    setManualExportError(null)
    try {
      sessionStorage.removeItem('ff:ce:entries')
      sessionStorage.removeItem('ff:ce:taskId')
      sessionStorage.removeItem('ff:ce:started')
    } catch {}
  }

  const runpodStatusColor = (status: string | null) =>
    status === 'COMPLETED' ? 'text-green-600' :
    status === 'FAILED' || status === 'TIMED_OUT' ? 'text-destructive' :
    'text-muted-foreground'

  return (
    <div className="max-w-2xl space-y-5 py-2">
      <div>
        <h2 className="font-semibold mb-1">Caption Export</h2>
        <p className="text-sm text-muted-foreground">
          Load images, run CrewAI captioning, download or upload a ZIP, then kick off LoRA training on RunPod.
        </p>
      </div>

      {/* Config — hidden in manual mode (no AI needed) */}
      <div className={`grid grid-cols-2 gap-4${source === 'manual' ? ' hidden' : ''}`}>
        <div className="space-y-2">
          <Label>Persona</Label>
          <Select value={persona} onValueChange={setPersona}>
            <SelectTrigger><SelectValue placeholder="Select persona" /></SelectTrigger>
            <SelectContent>
              {personas.map(p => (
                <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Vision Model</Label>
          <Select value={visionModel} onValueChange={setVisionModel}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {visionModels.map(m => (
                <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Source toggle — only shown before starting */}
      {!started && (
        <div className="space-y-3">
          <div className="flex gap-2">
            <button
              onClick={() => { setSource('local'); setEntries([]) }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
                source === 'local'
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-background border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              <Upload className="w-3.5 h-3.5" />
              Local Upload
            </button>
            <button
              onClick={() => { setSource('drive'); setEntries([]) }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
                source === 'drive'
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-background border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              <HardDrive className="w-3.5 h-3.5" />
              Google Drive
            </button>
            <button
              onClick={() => { setSource('manual'); setEntries([]); setManualCaptions({}); setManualExportResult(null); setManualExportError(null) }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
                source === 'manual'
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-background border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              <PenLine className="w-3.5 h-3.5" />
              Manual Captions
            </button>
          </div>

          {source === 'local' && (
            <label
              className="flex flex-col items-center justify-center w-full p-6 border-2 border-dashed border-muted-foreground/30 rounded-lg cursor-pointer hover:border-primary/50 hover:bg-muted/30 transition-colors"
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
              {uploadProgress
                ? <Loader2 className="w-6 h-6 animate-spin text-muted-foreground mb-2" />
                : <Upload className="w-6 h-6 text-muted-foreground mb-2" />}
              <p className="text-sm text-muted-foreground">
                {uploadProgress
                  ? `Uploading ${uploadProgress.current} / ${uploadProgress.total}...`
                  : 'Drop images here or click to upload'}
              </p>
              {uploadProgress && (
                <div className="w-full mt-2 bg-muted rounded-full h-1.5">
                  <div
                    className="bg-primary h-1.5 rounded-full transition-all duration-200"
                    style={{ width: `${Math.round((uploadProgress.current / uploadProgress.total) * 100)}%` }}
                  />
                </div>
              )}
              <p className="text-xs text-muted-foreground/60 mt-1">PNG, JPG, JPEG, WEBP • up to 30 images</p>
            </label>
          )}

          {source === 'drive' && (
            <div className="space-y-3 p-4 border rounded-lg bg-muted/20">
              <div className="space-y-1.5">
                <Label>Google Drive Folder URL</Label>
                <p className="text-xs text-muted-foreground">
                  Paste the Drive folder link — images will be downloaded and downscaled automatically.
                </p>
                <Input
                  placeholder="https://drive.google.com/drive/folders/..."
                  value={driveFolderUrl}
                  onChange={e => setDriveFolderUrl(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Downscale to (px, longest side)</Label>
                <Input
                  type="number"
                  min={256}
                  max={4096}
                  value={driveMaxDimension}
                  onChange={e => setDriveMaxDimension(Number(e.target.value))}
                  className="w-32"
                />
              </div>
              <Button
                onClick={() => void handleDriveFetch()}
                disabled={!driveFolderUrl.trim() || driveFetching}
                size="sm"
              >
                {driveFetching
                  ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />Fetching...</>
                  : <><HardDrive className="w-3.5 h-3.5 mr-1.5" />Fetch from Drive</>}
              </Button>
              {driveFetchError && (
                <p className="text-xs text-destructive mt-1">{driveFetchError}</p>
              )}
            </div>
          )}

          {source === 'manual' && (
            <div className="space-y-4">
              <label
                className="flex flex-col items-center justify-center w-full p-6 border-2 border-dashed border-muted-foreground/30 rounded-lg cursor-pointer hover:border-primary/50 hover:bg-muted/30 transition-colors"
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
                {uploadProgress
                  ? <Loader2 className="w-6 h-6 animate-spin text-muted-foreground mb-2" />
                  : <Upload className="w-6 h-6 text-muted-foreground mb-2" />}
                <p className="text-sm text-muted-foreground">
                  {uploadProgress
                    ? `Uploading ${uploadProgress.current} / ${uploadProgress.total}...`
                    : entries.length > 0 ? 'Drop more images to add' : 'Drop images here or click to upload'}
                </p>
                {uploadProgress && (
                  <div className="w-full mt-2 bg-muted rounded-full h-1.5">
                    <div
                      className="bg-primary h-1.5 rounded-full transition-all duration-200"
                      style={{ width: `${Math.round((uploadProgress.current / uploadProgress.total) * 100)}%` }}
                    />
                  </div>
                )}
                <p className="text-xs text-muted-foreground/60 mt-1">PNG, JPG, JPEG, WEBP • up to 30 images</p>
              </label>

              {entries.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">{entries.length} image{entries.length !== 1 ? 's' : ''} — paste a caption for each</p>
                  <div className="border rounded-lg divide-y max-h-[65vh] overflow-y-auto">
                    {entries.map(entry => (
                      <div key={entry.stem} className="flex gap-3 p-3 items-start">
                        <img
                          src={workspaceApi.getRefImageThumbnailUrl(entry.path.split('/').pop() ?? '')}
                          alt={entry.stem}
                          className="w-24 h-24 object-cover rounded shrink-0 bg-muted"
                        />
                        <div className="flex-1 space-y-1.5 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-mono text-muted-foreground truncate">{entry.stem}{entry.original_ext}</span>
                            <button
                              className="shrink-0 p-0.5 rounded text-muted-foreground hover:text-destructive transition-colors"
                              onClick={() => handleRemove(entry.stem)}
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                          <Textarea
                            rows={3}
                            placeholder="Paste caption here..."
                            value={manualCaptions[entry.stem] ?? ''}
                            onChange={e => setManualCaptions(prev => ({ ...prev, [entry.stem]: e.target.value }))}
                            className="text-xs resize-none"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* File list — hidden in manual mode (editor is shown inline above) */}
      {entries.length > 0 && source !== 'manual' && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground mb-2">{entries.length} image{entries.length !== 1 ? 's' : ''} queued</p>
          <div className="border rounded-lg divide-y max-h-64 overflow-y-auto">
            {entries.map((entry) => (
              <div key={entry.stem} className="flex items-center gap-2 px-3 py-2 text-sm">
                <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                <span className="flex-1 truncate font-mono text-xs">{entry.stem}{entry.original_ext}</span>
                <span className="text-xs text-muted-foreground shrink-0">→ {entry.stem}.txt</span>
                {!started && (
                  <button
                    className="shrink-0 p-0.5 rounded text-muted-foreground hover:text-destructive transition-colors"
                    onClick={() => handleRemove(entry.stem)}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Progress */}
      {started && task && (
        <Card className={task.state === 'FAILURE' ? 'border-destructive' : task.state === 'SUCCESS' ? 'border-green-500' : ''}>
          <CardContent className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm">{task.status_message || 'Processing...'}</p>
              <Badge variant={task.state === 'SUCCESS' ? 'success' : task.state === 'FAILURE' ? 'destructive' : 'secondary'}>
                {task.state}
              </Badge>
            </div>
            {task.progress > 0 && (
              <div className="space-y-1">
                <Progress value={task.progress} className="h-2" />
                <p className="text-xs text-right text-muted-foreground">{Math.round(task.progress)}%</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Actions row */}
      <div className="flex items-center gap-3 flex-wrap">
        {source === 'manual' ? (
          <>
            <Button
              onClick={() => void handleManualExport()}
              disabled={entries.length === 0 || manualExporting || uploadProgress !== null}
            >
              {manualExporting
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Exporting...</>
                : <><HardDrive className="w-4 h-4 mr-2" />Export &amp; Upload to Drive ({entries.length})</>}
            </Button>
            {entries.length > 0 && (
              <Button variant="outline" onClick={handleReset}>Reset</Button>
            )}
            {manualExportError && <p className="text-xs text-destructive w-full">{manualExportError}</p>}
          </>
        ) : !started ? (
          <Button
            onClick={() => void handleStart()}
            disabled={entries.length === 0 || !persona || uploadProgress !== null || driveFetching}
          >
            <Play className="w-4 h-4 mr-2" />
            Generate &amp; Export ({entries.length})
          </Button>
        ) : isDone ? (
          <>
            {task?.state === 'SUCCESS' && (
              <>
                <Button onClick={handleDownload}>
                  <Download className="w-4 h-4 mr-2" />
                  Download ZIP
                </Button>
                {!driveUploadResult && (
                  <div className="flex flex-col gap-1">
                    <Button
                      variant="outline"
                      onClick={() => void handleDriveUpload()}
                      disabled={driveUploading}
                    >
                      {driveUploading
                        ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Uploading...</>
                        : <><HardDrive className="w-4 h-4 mr-2" />Upload ZIP to Drive</>}
                    </Button>
                    {driveUploadError && (
                      <p className="text-xs text-destructive">{driveUploadError}</p>
                    )}
                  </div>
                )}
              </>
            )}
            <Button variant="outline" onClick={handleReset}>
              Start New Export
            </Button>
          </>
        ) : (
          <Button disabled>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Running...
          </Button>
        )}
      </div>

      {/* Manual export result */}
      {manualExportResult && (
        <div className="space-y-2 text-sm p-3 border rounded-lg bg-muted/20">
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>Uploaded <span className="font-mono">{manualExportResult.filename}</span> to Google Drive</span>
          </div>
          <div className="ml-6 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground shrink-0">Folder ID:</span>
              <span className="font-mono text-xs truncate">{manualExportResult.folderId}</span>
              <button
                onClick={() => void handleCopyFolderId(manualExportResult.folderId)}
                className="shrink-0 p-1 rounded hover:bg-muted transition-colors"
                title="Copy folder ID"
              >
                {copiedFolderId ? <CheckCircle2 className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3 text-muted-foreground" />}
              </button>
            </div>
            <a
              href={manualExportResult.publicUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground block truncate"
            >
              {manualExportResult.publicUrl}
            </a>
          </div>
        </div>
      )}

      {/* Drive upload confirmation */}
      {driveUploadResult && (
        <div className="space-y-1 text-sm">
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>Uploaded <span className="font-mono">{driveUploadResult.filename}</span> to Google Drive (public)</span>
          </div>
          <a
            href={driveUploadResult.publicUrl}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground ml-6 block truncate"
          >
            {driveUploadResult.publicUrl}
          </a>
        </div>
      )}

      {/* LoRA training config */}
      <>
        <Separator />
        <div className="space-y-4">
          <div>
            <h3 className="font-semibold text-sm mb-0.5">LoRA Training</h3>
            <p className="text-xs text-muted-foreground">
              Configure and submit a training job to RunPod. Paste a Drive file ID or URL as the dataset source.
            </p>
          </div>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label>Dataset Source</Label>
                <Input
                  placeholder="gdrive://<fileId> or Drive file ID"
                  value={loraConfig.dataset_source}
                  onChange={e => setLoraConfig(p => ({ ...p, dataset_source: e.target.value }))}
                  className="font-mono text-xs"
                />
              </div>

              <div className="space-y-1.5">
                <Label>LoRA Name</Label>
                <Input
                  placeholder="e.g. emi_v4"
                  value={loraConfig.lora_name}
                  onChange={e => setLoraConfig(p => ({ ...p, lora_name: e.target.value }))}
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <Label>Steps</Label>
                  <Input
                    type="number"
                    min={100}
                    step={100}
                    value={loraConfig.steps}
                    onChange={e => setLoraConfig(p => ({ ...p, steps: Number(e.target.value) }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Save Every</Label>
                  <Input
                    type="number"
                    min={100}
                    step={100}
                    value={loraConfig.save_every}
                    onChange={e => setLoraConfig(p => ({ ...p, save_every: Number(e.target.value) }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Sample Every</Label>
                  <Input
                    type="number"
                    min={100}
                    step={100}
                    value={loraConfig.sample_every}
                    onChange={e => setLoraConfig(p => ({ ...p, sample_every: Number(e.target.value) }))}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>Sample Prompts <span className="text-muted-foreground font-normal">(one per line)</span></Label>
                <Textarea
                  rows={5}
                  placeholder={"the girl in a coffee shop drinking a matcha latte\nthe girl going on a photoshoot, professional costume"}
                  value={loraConfig.sample_prompts}
                  onChange={e => setLoraConfig(p => ({ ...p, sample_prompts: e.target.value }))}
                  className="font-mono text-xs resize-none"
                />
              </div>
            </div>

            {/* Submit button */}
            <Button
              onClick={() => void handleRunpodSubmit()}
              disabled={!loraConfig.dataset_source || !loraConfig.lora_name || runpodSubmitting}
            >
              {runpodSubmitting
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Submitting...</>
                : <><Cpu className="w-4 h-4 mr-2" />Submit to RunPod</>}
            </Button>

            {/* Job history */}
            {!runpodJobsLoaded && (
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <Loader2 className="w-3 h-3 animate-spin" />Loading job history...
              </p>
            )}
            {runpodJobsLoaded && runpodJobs.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Training Jobs</p>
                <div className="space-y-2">
                  {runpodJobs.map(job => (
                    <RunpodJobCard
                      key={job.job_id}
                      job={job}
                      checking={checkingJobId === job.job_id}
                      onCheck={() => void handleRunpodCheckStatus(job.job_id, job.endpoint_id)}
                      statusColor={runpodStatusColor(job.status)}
                    />
                  ))}
                </div>
              </div>
            )}
        </div>
      </>
    </div>
  )
}

const RunpodJobCard: React.FC<{
  job: RunpodJobEntry
  checking: boolean
  onCheck: () => void
  statusColor: string
}> = ({ job, checking, onCheck, statusColor }) => {
  const [showJson, setShowJson] = useState(false)
  return (
    <div className="border rounded-lg p-3 space-y-2 text-sm">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-medium truncate">{job.lora_name}</span>
          <span className="text-xs text-muted-foreground shrink-0">
            {new Date(job.submitted_at).toLocaleString()}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {job.status && (
            <span className={`text-xs font-medium ${statusColor}`}>{job.status}</span>
          )}
          <Button size="sm" variant="outline" onClick={onCheck} disabled={checking}>
            {checking
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <RefreshCw className="w-3.5 h-3.5" />}
          </Button>
        </div>
      </div>
      <span className="text-xs text-muted-foreground font-mono truncate block">{job.job_id}</span>
      {job.output && (
        <pre className="text-xs bg-muted rounded p-2 overflow-x-auto max-h-32">
          {JSON.stringify(job.output, null, 2)}
        </pre>
      )}
      <button
        className="text-xs text-muted-foreground hover:text-foreground"
        onClick={() => setShowJson(v => !v)}
      >
        {showJson ? 'Hide' : 'Show'} training config
      </button>
      {showJson && (
        <pre className="text-xs bg-muted rounded p-2 overflow-x-auto max-h-40">
          {JSON.stringify(job.job_input, null, 2)}
        </pre>
      )}
    </div>
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
