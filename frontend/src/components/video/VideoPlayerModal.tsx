import React from 'react'
import { X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { VideoPreview } from './VideoPreview'
import { videoApi } from '@/api/video'
import { formatDistanceToNow } from 'date-fns'
import type { VideoItem } from '@/types/video'

interface VideoPlayerModalProps {
  video: VideoItem | null
  onClose: () => void
}

export const VideoPlayerModal: React.FC<VideoPlayerModalProps> = ({ video, onClose }) => {
  if (!video) return null

  const src = video.filename ? videoApi.getVideoUrl(video.filename) : ''
  const poster = video.filename ? videoApi.getThumbnailUrl(video.filename) : undefined

  const timeAgo = (() => {
    try {
      return formatDistanceToNow(new Date(video.created_at), { addSuffix: true })
    } catch {
      return video.created_at
    }
  })()

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-xl shadow-2xl w-full max-w-2xl p-6 relative"
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-base font-semibold mb-4 pr-8 truncate">
          {video.filename ?? `Video #${video.id}`}
        </h2>

        <VideoPreview src={src} poster={poster} />

        <div className="mt-4 space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="capitalize">{video.status}</Badge>
            <span className="text-xs text-muted-foreground">{timeAgo}</span>
          </div>
          {video.prompt && (
            <div>
              <p className="text-xs text-muted-foreground mb-0.5">Prompt</p>
              <p className="text-sm">{video.prompt}</p>
            </div>
          )}
          {video.source_image && (
            <div>
              <p className="text-xs text-muted-foreground mb-0.5">Source Image</p>
              <p className="text-sm font-mono text-xs text-muted-foreground break-all">
                {video.source_image}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
