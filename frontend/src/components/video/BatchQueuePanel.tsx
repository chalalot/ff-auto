import React from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ListChecks, Loader2, Send } from 'lucide-react'
import { reviewApi } from '@/api/review'
import type { ReviewItemCreate } from '@/types/review'
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

export const BatchQueuePanel: React.FC<BatchQueuePanelProps> = ({
  items,
  klingSettings,
  backend = 'api',
  comfySettings,
}) => {
  const [sentCount, setSentCount] = React.useState<number | null>(null)

  const mutation = useMutation({
    mutationFn: (reviewItems: ReviewItemCreate[]) =>
      reviewApi.createRequests({ items: reviewItems }),
  })

  const handleSend = async () => {
    if (items.length === 0) return
    const provider = backend === 'comfy' ? 'comfy_video' : 'kling'
    const settings = backend === 'comfy'
      ? ((comfySettings ?? {}) as Record<string, unknown>)
      : (klingSettings as unknown as Record<string, unknown>)
    const reviewItems: ReviewItemCreate[] = items.flatMap(item =>
      Array.from({ length: item.variation_count }, () => ({
        source_image_path: item.image_path,
        prompt: item.prompt ?? '',
        provider,
        workflow_name: backend === 'comfy' ? 'kling.json' : null,
        settings,
      }))
    )
    const res = await mutation.mutateAsync(reviewItems)
    setSentCount(res.request_ids.length)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">Send to Review Queue</p>
            <Badge variant="outline" className="text-xs">
              {backend === 'comfy' ? 'ComfyUI' : 'Kling API'}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {items.length} image{items.length !== 1 ? 's' : ''} — nothing generates until approved in the queue
          </p>
        </div>
        <Button
          onClick={() => void handleSend()}
          disabled={items.length === 0 || mutation.isPending}
        >
          {mutation.isPending
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Sending...</>
            : <><Send className="w-4 h-4 mr-2" />Send to Review Queue</>
          }
        </Button>
      </div>

      {mutation.isError && (
        <p className="text-sm text-destructive">Failed to send to review queue. Please try again.</p>
      )}

      {sentCount !== null && (
        <div className="flex items-center gap-2 rounded-md border p-3 text-sm">
          <ListChecks className="w-4 h-4 text-muted-foreground" />
          <span>{sentCount} request{sentCount !== 1 ? 's' : ''} awaiting review.</span>
          <Link to="/review" className="text-primary hover:underline">Open Review Queue</Link>
        </div>
      )}
    </div>
  )
}
