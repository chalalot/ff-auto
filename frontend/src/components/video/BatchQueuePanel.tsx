import React from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Loader2, Send } from 'lucide-react'
import { useVideoBatchGenerate } from '@/hooks/useVideoGenerate'
import { useVideoStatus } from '@/hooks/useVideoStatus'
import type { KlingSettings, VideoBackend, ComfyKlingSettings } from '@/types/video'

interface QueueItem {
  image_path: string
  prompt?: string
  variation_count: number
}

interface BatchQueuePanelProps {
  items: QueueItem[]
  klingSettings: KlingSettings
  backend?: VideoBackend
  comfySettings?: ComfyKlingSettings
}

const STATUS_BADGE: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  processing: 'default',
  completed: 'outline',
  succeed: 'outline',
  failed: 'destructive',
}

const TaskCard: React.FC<{ taskId: string; label: string; backend: VideoBackend }> = ({ taskId, label, backend }) => {
  const { data } = useVideoStatus(taskId, backend)
  const status = data?.status ?? 'pending'
  const progress = data?.progress ?? 0
  const variant = STATUS_BADGE[status] ?? 'secondary'

  return (
    <div className="rounded-md border p-3 space-y-2" data-testid="task-progress-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm truncate">{label}</p>
        <Badge variant={variant} className="text-xs shrink-0 capitalize">{status}</Badge>
      </div>
      {(status === 'pending' || status === 'processing' || !['completed', 'succeed', 'failed'].includes(status)) && (
        <Progress value={progress} className="h-1.5" />
      )}
      {(status === 'completed' || status === 'succeed') && data?.video_url && (
        <a
          href={data.video_url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-primary hover:underline"
        >
          View video
        </a>
      )}
    </div>
  )
}

export const BatchQueuePanel: React.FC<BatchQueuePanelProps> = ({
  items,
  klingSettings,
  backend = 'api',
  comfySettings,
}) => {
  const [taskIds, setTaskIds] = React.useState<Array<{ id: string; label: string }>>([])
  const mutation = useVideoBatchGenerate()

  const handleQueue = async () => {
    if (items.length === 0) return
    const res = await mutation.mutateAsync({
      items,
      kling_settings: klingSettings,
      backend,
      comfy_settings: comfySettings,
    })
    const labels = items.map(it => it.image_path.split('/').pop() ?? it.image_path)
    const newTasks = res.task_ids.map((id, i) => ({
      id,
      label: labels[i] ?? id,
    }))
    setTaskIds(prev => [...prev, ...newTasks])
  }

  const buttonLabel = backend === 'comfy' ? 'Queue via ComfyUI' : 'Queue to Kling'
  const pendingLabel = backend === 'comfy' ? 'Queuing to ComfyUI...' : 'Queuing...'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">{buttonLabel}</p>
            <Badge variant="outline" className="text-xs">
              {backend === 'comfy' ? 'ComfyUI' : 'Kling API'}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {items.length} image{items.length !== 1 ? 's' : ''} ready to process
          </p>
        </div>
        <Button
          onClick={() => void handleQueue()}
          disabled={items.length === 0 || mutation.isPending}
        >
          {mutation.isPending
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{pendingLabel}</>
            : <><Send className="w-4 h-4 mr-2" />{buttonLabel}</>
          }
        </Button>
      </div>

      {mutation.isError && (
        <p className="text-sm text-destructive">Failed to queue batch. Please try again.</p>
      )}

      {taskIds.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground uppercase tracking-wide">Progress</p>
          {taskIds.map(t => (
            <TaskCard key={t.id} taskId={t.id} label={t.label} backend={backend} />
          ))}
        </div>
      )}
    </div>
  )
}
