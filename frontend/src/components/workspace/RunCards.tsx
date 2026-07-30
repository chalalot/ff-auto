// Cards for things the worker has run or is running: a live task, a pipeline
// run, a legacy execution. Extracted from WorkspacePage so the Flow surface's
// Generating panel and the Library's History tab share one implementation.
import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { ExternalLink, FileText, Image as ImageIcon, Info, Loader2, X, Zap } from 'lucide-react'
import { workspaceApi } from '@/api/workspace'
import { pipelineApi } from '@/api/pipeline'
import { useTaskProgress } from '@/hooks/useTaskProgress'
import type { ActiveTask, ExecutionRecord } from '@/types'
import type { PipelineRunSummary } from '@/types/pipeline'

// Mirrors IN_FLIGHT in backend/database/pipeline_runs_storage.py — the statuses
// that mean "no worker has finished this yet".
const IN_FLIGHT: string[] = ['queued', 'running']

function refFilenameFromPath(refPath?: string): string | null {
  if (!refPath) return null
  return refPath.split('/').pop() ?? null
}

function formatPipelineName(name: string) {
  return name.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase())
}

export const InfoModal: React.FC<{ title: string; onClose: () => void; children: React.ReactNode }> = ({ title, onClose, children }) => (
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

// Shows a task from the shared Redis registry. Adds live 1s polling on top of
// the 5s global refresh.
export const GlobalTaskCard: React.FC<{ task: ActiveTask }> = ({ task }) => {
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

export const PipelineRunHistoryCard: React.FC<{ run: PipelineRunSummary }> = ({ run }) => {
  const input = run.input_payload && typeof run.input_payload === 'object'
    ? run.input_payload as Record<string, unknown>
    : null
  const refFilename = refFilenameFromPath(typeof input?.image_path === 'string' ? input.image_path : undefined)
  const status: 'success' | 'destructive' | 'secondary' = run.status === 'succeeded' ? 'success' : run.status === 'failed' ? 'destructive' : 'secondary'

  const queryClient = useQueryClient()
  const failMutation = useMutation({
    mutationFn: () => pipelineApi.markFailed(run.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['pipeline-runs'] }),
  })

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
        {/* A queued run that was never picked up (or a running one whose worker
            died) never reaches a terminal state on its own, and while it sits
            there the history list keeps refetching every 5s for work that isn't
            happening. This is its only exit. */}
        {IN_FLIGHT.includes(run.status) && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 shrink-0 text-xs"
            disabled={failMutation.isPending}
            onClick={() => failMutation.mutate()}
          >
            {failMutation.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              'Mark failed'
            )}
          </Button>
        )}
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

export const ExecutionCard: React.FC<{ exec: ExecutionRecord }> = ({ exec }) => {
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
