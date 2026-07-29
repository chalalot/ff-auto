// The Caption Export tab: image upload → CrewAI captioning → ZIP/Drive
// delivery, plus RunPod LoRA training jobs and the Hugging Face upload.
// Extracted verbatim from WorkspacePage; mirrors backend/api/exports.py.
import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'
import { useTaskProgress } from '@/hooks/useTaskProgress'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { Play, Loader2, Upload, Trash2, X, Download, FileText, HardDrive, CheckCircle2, Cpu, PenLine, Copy, ExternalLink, BookOpen } from 'lucide-react'
import { resolveDroppedFiles, uploadErrorMessage } from '@/lib/uploads'
import type { ProcessImageConfig, ActiveTask, CaptionExportEntry } from '@/types'

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
  check_error?: string | null
}

type RunpodJobInput = Parameters<typeof workspaceApi.runpodSubmit>[0]['job_input']

const RUNPOD_ACTIVE_STATUSES = new Set(['IN_QUEUE', 'IN_PROGRESS'])
const RUNPOD_RETRYABLE_STATUSES = new Set(['EXPIRED', 'FAILED', 'TIMED_OUT', 'CANCELLED'])

const DEFAULT_LORA: LoraConfig = {
  dataset_source: '',
  lora_name: '',
  steps: 2000,
  save_every: 500,
  sample_every: 500,
  sample_prompts: '',
}

const normalizeRunpodJobInput = (input: Record<string, unknown>): RunpodJobInput => ({
  dataset_source: String(input.dataset_source ?? ''),
  lora_name: String(input.lora_name ?? ''),
  steps: Number(input.steps ?? DEFAULT_LORA.steps),
  save_every: Number(input.save_every ?? DEFAULT_LORA.save_every),
  sample_every: Number(input.sample_every ?? DEFAULT_LORA.sample_every),
  sample_prompts: Array.isArray(input.sample_prompts)
    ? input.sample_prompts.map(String).filter(Boolean)
    : typeof input.sample_prompts === 'string'
      ? input.sample_prompts.split('\n').map(s => s.trim()).filter(Boolean)
      : [],
})

export const CaptionExportTab: React.FC<{
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
  const [dropError, setDropError] = useState<string | null>(null)
  const [taskId, setTaskId] = useState<string | null>(() => {
    try { return sessionStorage.getItem('ff:ce:taskId') } catch { return null }
  })
  const [started, setStarted] = useState(() => {
    try { return sessionStorage.getItem('ff:ce:started') === '1' } catch { return false }
  })

  // Persist session state so navigation away doesn't wipe the run
  React.useEffect(() => {
    try { sessionStorage.setItem('ff:ce:entries', JSON.stringify(entries)) } catch { /* sessionStorage may be unavailable */ }
  }, [entries])
  React.useEffect(() => {
    try {
      if (taskId) sessionStorage.setItem('ff:ce:taskId', taskId)
      else sessionStorage.removeItem('ff:ce:taskId')
    } catch { /* sessionStorage may be unavailable */ }
  }, [taskId])
  React.useEffect(() => {
    try { sessionStorage.setItem('ff:ce:started', started ? '1' : '0') } catch { /* sessionStorage may be unavailable */ }
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

  // Caption export history
  type ExportHistoryEntry = { id: number; file_id: string; filename: string; public_url: string; image_count: number; exported_at: string }
  const [exportHistory, setExportHistory] = useState<ExportHistoryEntry[]>([])
  const [exportHistoryLoaded, setExportHistoryLoaded] = useState(false)
  const [copiedExportId, setCopiedExportId] = useState<number | null>(null)
  React.useEffect(() => {
    workspaceApi.captionExportHistory()
      .then(data => setExportHistory(data))
      .catch(err => console.error('Failed to load export history:', err))
      .finally(() => setExportHistoryLoaded(true))
  }, [])

  // Auto-refresh active jobs every 10s
  const hasActiveJobs = runpodJobs.some(j => !j.status || RUNPOD_ACTIVE_STATUSES.has(j.status))
  React.useEffect(() => {
    if (!hasActiveJobs) return
    const timer = setInterval(async () => {
      const active = runpodJobs.filter(j => !j.status || RUNPOD_ACTIVE_STATUSES.has(j.status))
      await Promise.all(active.map(async j => {
        try {
          const data = await workspaceApi.runpodStatus(j.job_id, j.endpoint_id)
          setRunpodJobs(prev => prev.map(p =>
            p.job_id === j.job_id
              ? { ...p, status: data.status ?? null, output: (data.output as Record<string, unknown> | null | undefined) ?? null, check_error: null }
              : p
          ))
        } catch (err: unknown) {
          const httpStatus = (err as { response?: { status?: number } })?.response?.status
          if (httpStatus === 404) {
            setRunpodJobs(prev => prev.map(p =>
              p.job_id === j.job_id ? { ...p, status: 'EXPIRED', output: null, check_error: null } : p
            ))
          } else {
            const detail =
              (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
              (err instanceof Error ? err.message : 'Status check failed')
            setRunpodJobs(prev => prev.map(p =>
              p.job_id === j.job_id ? { ...p, check_error: detail } : p
            ))
          }
        }
      }))
    }, 10_000)
    return () => clearInterval(timer)
  }, [hasActiveJobs, runpodJobs])

  // Sync persona default once it's loaded
  React.useEffect(() => {
    if (!persona && defaultConfig.persona) setPersona(defaultConfig.persona)
  }, [defaultConfig.persona]) // eslint-disable-line react-hooks/exhaustive-deps

  // Pre-fill dataset_source when Drive upload completes (either flow)
  React.useEffect(() => {
    if (driveUploadResult?.fileId) {
      setLoraConfig(prev => ({ ...prev, dataset_source: `gdrive://${driveUploadResult.fileId}` }))
    }
  }, [driveUploadResult])
  React.useEffect(() => {
    if (manualExportResult?.fileId) {
      setLoraConfig(prev => ({ ...prev, dataset_source: `gdrive://${manualExportResult.fileId}` }))
    }
  }, [manualExportResult])

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

  const [showInstructions, setShowInstructions] = useState(false)
  const { data: instructions, isFetching: instructionsFetching } = useQuery({
    queryKey: ['persona-instructions', persona],
    queryFn: () => workspaceApi.getPersonaInstructions(persona),
    enabled: showInstructions && !!persona,
    staleTime: 60_000,
  })

  const handleUpload = async (files: FileList | File[] | null) => {
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

  const handleDrop = async (dt: DataTransfer) => {
    if (uploadProgress !== null) return
    setDropError(null)
    try {
      const files = await resolveDroppedFiles(dt)
      if (files.length === 0) {
        setDropError('No image found in the dropped content')
        return
      }
      await handleUpload(files)
    } catch (err) {
      setDropError(uploadErrorMessage(err))
    }
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

  const handleRunpodRetry = async (job: RunpodJobEntry) => {
    try {
      const jobInput = normalizeRunpodJobInput(job.job_input)
      const res = await workspaceApi.runpodSubmit({ job_input: jobInput })
      setRunpodJobs(prev => [{
        job_id: res.job_id,
        endpoint_id: res.endpoint_id,
        lora_name: job.lora_name,
        submitted_at: new Date().toISOString(),
        job_input: jobInput,
        status: null,
        output: null,
      }, ...prev])
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Retry failed'
      alert(detail)
    }
  }

  const handleManualExport = async () => {
    if (entries.length === 0) return
    setManualExporting(true)
    setManualExportError(null)
    try {
      const res = await workspaceApi.captionExportManualToDrive({ entries, captions: manualCaptions })
      setManualExportResult({ fileId: res.file_id, folderId: res.folder_id, filename: res.filename, publicUrl: res.public_url })
      setExportHistory(prev => [{
        id: Date.now(),
        file_id: res.file_id,
        filename: res.filename,
        public_url: res.public_url,
        image_count: entries.length,
        exported_at: new Date().toISOString(),
      }, ...prev])
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
      workflow_type: 'image_generation',
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
    } catch { /* sessionStorage may be unavailable */ }
  }

  const runpodStatusColor = (status: string | null) =>
    status === 'COMPLETED' ? 'text-green-600' :
    status === 'EXPIRED' ? 'text-yellow-600' :
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
          <div className="flex items-center justify-between">
            <Label>Persona</Label>
            {persona && (
              <button
                onClick={() => setShowInstructions(true)}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <BookOpen className="w-3 h-3" />
                View instructions
              </button>
            )}
          </div>
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
              onDrop={(e) => { e.preventDefault(); void handleDrop(e.dataTransfer) }}
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
              {dropError && <p className="text-xs text-destructive mt-1">{dropError}</p>}
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
              <span className="text-xs text-muted-foreground shrink-0">Dataset source:</span>
              <span className="font-mono text-xs truncate">gdrive://{manualExportResult.fileId}</span>
              <button
                onClick={() => void handleCopyFolderId(`gdrive://${manualExportResult.fileId}`)}
                className="shrink-0 p-1 rounded hover:bg-muted transition-colors"
                title="Copy dataset source"
              >
                {copiedFolderId ? <CheckCircle2 className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3 text-muted-foreground" />}
              </button>
            </div>
            <a
              href={manualExportResult.publicUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              View in Drive ↗
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

      {/* Caption export history */}
      {exportHistoryLoaded && exportHistory.length > 0 && (
        <>
          <Separator />
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Past Exports</p>
            <div className="space-y-1.5">
              {exportHistory.map(entry => (
                <div key={entry.id} className="border rounded-lg px-3 py-2 flex items-center gap-3 text-xs">
                  <div className="flex-1 min-w-0 space-y-0.5">
                    <span className="font-mono font-medium truncate block">{entry.filename}</span>
                    <span className="text-muted-foreground">
                      {entry.image_count} image{entry.image_count !== 1 ? 's' : ''} · {new Date(entry.exported_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <a
                      href={entry.public_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-muted-foreground hover:text-foreground"
                      title="View in Drive"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                    <button
                      className="p-1 rounded hover:bg-muted transition-colors"
                      title="Copy dataset source"
                      onClick={async () => {
                        await navigator.clipboard.writeText(`gdrive://${entry.file_id}`)
                        setCopiedExportId(entry.id)
                        setLoraConfig(prev => ({ ...prev, dataset_source: `gdrive://${entry.file_id}` }))
                        setTimeout(() => setCopiedExportId(null), 1500)
                      }}
                    >
                      {copiedExportId === entry.id
                        ? <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
                        : <Copy className="w-3.5 h-3.5 text-muted-foreground" />}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
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
                      onRetry={() => void handleRunpodRetry(job)}
                      onCancel={() => setRunpodJobs(prev => prev.map(p => p.job_id === job.job_id ? { ...p, status: 'CANCELLED' } : p))}
                      onDelete={() => setRunpodJobs(prev => prev.filter(p => p.job_id !== job.job_id))}
                      statusColor={runpodStatusColor(job.status)}
                    />
                  ))}
                </div>
              </div>
            )}
        </div>
      </>

      {/* Instructions modal */}
      {showInstructions && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowInstructions(false)}>
          <div
            className="bg-background border rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col mx-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
              <div className="flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-muted-foreground" />
                <span className="font-semibold text-sm">
                  Instructions — {persona}
                </span>
              </div>
              <button onClick={() => setShowInstructions(false)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 p-4 space-y-4 text-sm">
              {instructionsFetching ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />Loading...
                </div>
              ) : instructions ? (
                <>
                  {[
                    { label: 'System Prompt (agent_system.txt)', content: instructions.agent_system },
                    { label: 'Identity Lock (personas/' + persona + '/identity_lock.txt)', content: instructions.identity_lock },
                  ].filter(s => s.content).map(section => (
                    <div key={section.label}>
                      <p className="text-xs font-medium text-muted-foreground mb-1.5">{section.label}</p>
                      <pre className="text-xs bg-muted rounded-lg p-3 whitespace-pre-wrap break-words font-mono leading-relaxed">{section.content}</pre>
                    </div>
                  ))}
                </>
              ) : (
                <p className="text-muted-foreground text-xs">No instructions found.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

type RunpodOutputFile = { name: string; url: string }
type RunpodSample = { step: number; idx: number; url: string }

function parseRunpodOutput(output: Record<string, unknown>): {
  files: RunpodOutputFile[]
  samples: RunpodSample[]
} {
  const files: RunpodOutputFile[] = []
  const samples: RunpodSample[] = []

  const visit = (obj: unknown, keyPath: string) => {
    if (typeof obj === 'string' && (obj.startsWith('https://') || obj.startsWith('http://'))) {
      // filename = last path segment only (split on / to preserve extensions like .safetensors)
      const name = keyPath.split('/').filter(Boolean).at(-1) ?? keyPath
      // sample pattern: {timestamp}__{step}_{idx}.jpg
      const m = name.match(/^\d+__(\d+)_(\d+)\.(jpg|png)$/i)
      if (m) {
        samples.push({ step: parseInt(m[1]), idx: parseInt(m[2]), url: obj })
      } else {
        files.push({ name, url: obj })
      }
    } else if (obj && typeof obj === 'object') {
      for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
        visit(v, keyPath ? `${keyPath}/${k}` : k)
      }
    }
  }

  visit(output, '')
  // sort samples by step then idx
  samples.sort((a, b) => a.step - b.step || a.idx - b.idx)
  return { files, samples }
}

function extractRunpodError(output: Record<string, unknown> | null): { summary: string; detail: string } | null {
  if (!output) return null

  const detail =
    typeof output.traceback === 'string' ? output.traceback :
    typeof output.error === 'string' ? output.error :
    typeof output.message === 'string' ? output.message :
    typeof output.detail === 'string' ? output.detail :
    typeof output.stderr === 'string' ? output.stderr :
    typeof output.logs === 'string' ? output.logs :
    JSON.stringify(output, null, 2)

  if (!detail) return null

  const lines = detail
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)

  const gdrivePermissionLine = lines.find(line => line.includes('Cannot retrieve the public link of the file'))
  if (gdrivePermissionLine) {
    return {
      summary: 'Cannot retrieve the public Google Drive link. Check that the file is shared with anyone who has the link.',
      detail,
    }
  }

  const exceptionLine = [...lines]
    .reverse()
    .find(line => /(?:Error|Exception):/.test(line) && !line.startsWith('File '))

  return {
    summary: exceptionLine ?? lines[0] ?? 'Training job failed.',
    detail,
  }
}

const RunpodJobCard: React.FC<{
  job: RunpodJobEntry
  onRetry: () => void
  onCancel: () => void
  onDelete: () => void
  statusColor: string
}> = ({ job, onRetry, onCancel, onDelete, statusColor }) => {
  const [showJson, setShowJson] = useState(false)
  const [hfUploading, setHfUploading] = useState<string | null>(null) // filename being uploaded
  const [hfResults, setHfResults] = useState<Record<string, string>>({}) // filename → hf url
  const [cancelling, setCancelling] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const isActive = !job.status || job.status === 'IN_QUEUE' || job.status === 'IN_PROGRESS'
  const isDone = job.status === 'COMPLETED'
  const isRetryable = !!job.status && RUNPOD_RETRYABLE_STATUSES.has(job.status)

  const handleCancel = async () => {
    setCancelling(true)
    try {
      await workspaceApi.runpodCancel(job.job_id, job.endpoint_id)
      onCancel()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Cancel failed'
      alert(detail)
    } finally {
      setCancelling(false)
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await workspaceApi.runpodDeleteJob(job.job_id)
      onDelete()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Delete failed'
      alert(detail)
    } finally {
      setDeleting(false)
    }
  }
  const jobError = extractRunpodError(job.output)
  const { files: outputFiles, samples: outputSamples } = isDone && job.output
    ? parseRunpodOutput(job.output)
    : { files: [], samples: [] }

  const handleHfUpload = async (filename: string, fileUrl: string) => {
    setHfUploading(filename)
    try {
      const res = await workspaceApi.runpodUploadToHF({ file_url: fileUrl, lora_name: job.lora_name })
      setHfResults(prev => ({ ...prev, [filename]: res.url }))
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Upload failed'
      alert(detail)
    } finally {
      setHfUploading(null)
    }
  }

  // group samples by step
  const samplesByStep = outputSamples.reduce<Record<number, RunpodSample[]>>((acc, s) => {
    ;(acc[s.step] ??= []).push(s)
    return acc
  }, {})
  const sampleSteps = Object.keys(samplesByStep).map(Number).sort((a, b) => a - b)

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
          {isActive && (
            <button
              className="text-xs text-muted-foreground hover:text-destructive underline underline-offset-2 font-medium shrink-0 flex items-center gap-1"
              onClick={() => void handleCancel()}
              disabled={cancelling}
            >
              {cancelling ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              Cancel
            </button>
          )}
          <button
            className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 font-medium shrink-0"
            onClick={onRetry}
          >
            Retry
          </button>
          <button
            className="text-xs text-muted-foreground hover:text-destructive shrink-0 flex items-center gap-0.5"
            onClick={() => void handleDelete()}
            disabled={deleting}
            title="Remove from history"
          >
            {deleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
          </button>
          {job.status && (
            <span className={`text-xs font-medium flex items-center gap-1 ${statusColor}`}>
              {isActive && <Loader2 className="w-3 h-3 animate-spin" />}
              {job.status}
            </span>
          )}
        </div>
      </div>
      <span className="text-xs text-muted-foreground font-mono truncate block">{job.job_id}</span>

      {job.check_error && (
        <p className="text-xs text-yellow-700 dark:text-yellow-400">⚠ Status check failed: {job.check_error}</p>
      )}

      {isRetryable && (
        <div className="space-y-2 text-xs text-yellow-700 bg-yellow-50 dark:bg-yellow-950/30 rounded px-2 py-1.5">
          <span>
            {jobError?.summary ?? (job.status === 'EXPIRED' ? 'Output expired before it was captured.' : `Job ended with status ${job.status}.`)}
          </span>
          {jobError && (
            <details>
              <summary className="cursor-pointer font-medium">Error details</summary>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-background/70 p-2 text-[11px] text-foreground">
                {jobError.detail}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* Output files */}
      {outputFiles.length > 0 && (
        <div className="border-t pt-2 space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Output files</p>
          {outputFiles.map(({ name, url }) => {
            const isSafetensors = name.endsWith('.safetensors')
            const hfUrl = hfResults[name]
            const uploading = hfUploading === name
            return (
              <div key={name} className="flex items-center gap-1.5 rounded px-2 py-1 hover:bg-muted transition-colors group">
                <a href={url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 flex-1 min-w-0">
                  <Download className="w-3.5 h-3.5 shrink-0 text-muted-foreground group-hover:text-foreground" />
                  <span className="text-xs font-mono font-medium truncate">{name}</span>
                </a>
                {isSafetensors && (
                  hfUrl ? (
                    <a
                      href={hfUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-orange-500 hover:underline shrink-0 font-medium"
                    >
                      HF ↗
                    </a>
                  ) : (
                    <button
                      className="text-xs text-muted-foreground hover:text-orange-500 shrink-0 flex items-center gap-0.5 transition-colors"
                      disabled={!!hfUploading}
                      onClick={() => void handleHfUpload(name, url)}
                    >
                      {uploading
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : '↑ HF'}
                    </button>
                  )
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Sample images grouped by step */}
      {sampleSteps.length > 0 && (
        <div className="border-t pt-2 space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Sample images</p>
          {sampleSteps.map(step => (
            <div key={step}>
              <p className="text-xs text-muted-foreground mb-1">Step {step.toLocaleString()}</p>
              <div className="flex flex-wrap gap-1">
                {samplesByStep[step].map((s, i) => (
                  <a key={i} href={s.url} target="_blank" rel="noopener noreferrer">
                    <img
                      src={s.url}
                      alt={`step ${step} #${s.idx}`}
                      className="w-16 h-16 object-cover rounded border hover:opacity-80 transition-opacity"
                    />
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
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
