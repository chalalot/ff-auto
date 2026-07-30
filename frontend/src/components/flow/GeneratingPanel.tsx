import React from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { AlertTriangle, ArrowRight, Loader2, Type, Zap } from 'lucide-react'
import { reviewApi } from '@/api/review'
import { workspaceApi } from '@/api/workspace'
import { toast } from '@/hooks/useToast'
import { useActiveTasks } from '@/hooks/useActiveTasks'
import { useReviewRequests } from '@/hooks/useReviewRequests'
import { GlobalTaskCard } from '@/components/workspace/RunCards'
import { IMAGE_PROVIDERS, PROVIDER_LABEL } from '@/lib/providers'
import type { ReviewRequestItem } from '@/types/review'

// How long a dispatched row may sit before we stop believing in it. A row has
// no Celery task of its own, so if the worker died between begin_dispatch and
// its callback nothing will ever move it — and until it is reaped it keeps the
// rail's Generating chip amber and the queue polling at 5s. Video providers
// legitimately run long, hence the split.
const STALE_AFTER_MIN: Record<string, number> = { comfy_video: 90, kling: 90 }
const DEFAULT_STALE_AFTER_MIN = 20

// States the backend holds in the registry rather than pruning on sight — a
// crashed run is kept for _FAILED_GRACE so it can be read and then cleared.
const STOPPED_STATES = new Set(['FAILURE', 'SUCCESS', 'REVOKED'])

const staleSince = (item: ReviewRequestItem): boolean => {
  if (!item.updated_at) return false
  const limit = (STALE_AFTER_MIN[item.provider] ?? DEFAULT_STALE_AFTER_MIN) * 60_000
  return Date.now() - new Date(item.updated_at).getTime() > limit
}

// A row the review queue has handed to a provider. It has no Celery task of its
// own to poll, so the queue's own 5s refresh is what moves it along.
const DispatchedRow: React.FC<{ item: ReviewRequestItem }> = ({ item }) => {
  const queryClient = useQueryClient()
  const stale = staleSince(item)

  const failMutation = useMutation({
    mutationFn: () => reviewApi.markFailed(item.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['review-requests'] })
      toast({
        title: 'Marked failed',
        description: 'The row is in Prompt Review › Failed, where you can retry or discard it.',
        action: { label: 'Open Prompt Review', to: '/flow?stage=prompts' },
      })
    },
  })

  return (
    <Card className={stale ? 'border-destructive/40' : undefined}>
      <CardContent className="flex items-start gap-3 p-3">
        {item.source_image_path ? (
          <img
            src={reviewApi.getThumbnailUrl(item.id)}
            alt=""
            className="h-12 w-12 shrink-0 rounded-md border bg-muted object-cover"
            onError={e => { (e.currentTarget as HTMLImageElement).style.visibility = 'hidden' }}
          />
        ) : (
          // Text to image: no source image, so no thumbnail to ask for.
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border bg-muted">
            <Type className="h-4 w-4 text-muted-foreground/60" aria-hidden="true" />
          </div>
        )}
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            {stale ? (
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" />
            ) : (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-amber-600 dark:text-amber-400" />
            )}
            <span className="text-sm font-medium">
              {PROVIDER_LABEL[item.provider] ?? item.provider}
            </span>
            {item.workflow_name && (
              <Badge variant="outline" className="text-xs">
                {item.workflow_name.replace(/\.json$/i, '')}
              </Badge>
            )}
            <span className="ml-auto shrink-0 text-xs text-muted-foreground">
              {item.updated_at
                ? formatDistanceToNow(new Date(item.updated_at), { addSuffix: true })
                : 'just now'}
            </span>
          </div>
          <p className="line-clamp-2 text-xs text-muted-foreground">{item.prompt}</p>
          {stale && (
            <div className="flex items-center gap-2 pt-1">
              <p className="text-xs text-destructive">
                No result yet — the worker probably never reported back.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="ml-auto h-7 text-xs"
                disabled={failMutation.isPending}
                onClick={() => failMutation.mutate()}
              >
                {failMutation.isPending ? (
                  <><Loader2 className="mr-1.5 h-3 w-3 animate-spin" />Marking…</>
                ) : (
                  'Mark failed'
                )}
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Everything the machines are working on, in one list: Celery tasks (the prompt
// pipeline, caption exports, direct ComfyUI runs) and review rows already
// handed to a provider.
export const GeneratingPanel: React.FC = () => {
  const queryClient = useQueryClient()
  const { data: activeTasks = [] } = useActiveTasks()
  // Image work only — video generation is watched on the Video page.
  const { data: review } = useReviewRequests(IMAGE_PROVIDERS)

  const dispatched = (review?.items ?? []).filter(i => i.status === 'dispatched')
  const failed = review?.status_counts?.failed ?? 0
  const nothingRunning = activeTasks.length === 0 && dispatched.length === 0

  // Crashed tasks are held for 15 minutes so they can be read. Once read, one
  // click should clear the lot rather than an X per card.
  const stoppedTasks = activeTasks.filter(t => STOPPED_STATES.has(t.state))
  const clearStopped = useMutation({
    mutationFn: () => Promise.all(stoppedTasks.map(t => workspaceApi.dismissActiveTask(t.task_id))),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['workspace', 'active-tasks'] }),
  })

  return (
    <div className="space-y-4 px-4 py-4">
      {/* A failure mid-generation turns the rail chip red, but the rows live in
          Prompt Review — that's where they can be retried. */}
      {failed > 0 && (
        <Link
          to="/flow?stage=prompts"
          className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10"
        >
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            {failed} {failed === 1 ? 'generation' : 'generations'} failed
          </span>
          <span className="ml-auto inline-flex items-center gap-1 text-xs font-medium">
            Retry in Prompt Review
            <ArrowRight className="h-3 w-3" aria-hidden="true" />
          </span>
        </Link>
      )}

      {stoppedTasks.length > 1 && (
        <div className="flex items-center justify-end">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            disabled={clearStopped.isPending}
            onClick={() => clearStopped.mutate()}
          >
            {clearStopped.isPending ? (
              <><Loader2 className="mr-1.5 h-3 w-3 animate-spin" />Clearing…</>
            ) : (
              `Clear ${stoppedTasks.length} finished`
            )}
          </Button>
        </div>
      )}

      {nothingRunning ? (
        <div className="py-16 text-center text-muted-foreground">
          <Zap className="mx-auto mb-4 h-12 w-12 opacity-50" />
          <p>Nothing generating</p>
          <p className="mt-1 text-xs">Refreshes every 5 seconds while a worker is busy</p>
        </div>
      ) : (
        <div className="space-y-3">
          {activeTasks.map(task => (
            <GlobalTaskCard key={task.task_id} task={task} />
          ))}
          {dispatched.map(item => (
            <DispatchedRow key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  )
}
