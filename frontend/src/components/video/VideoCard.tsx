import React from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Trash2, Film } from 'lucide-react'
import { videoApi } from '@/api/video'
import type { VideoItem } from '@/types/video'

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  processing: 'default',
  succeed: 'outline',
  completed: 'outline',
  failed: 'destructive',
}

interface VideoCardProps {
  video: VideoItem
  selected: boolean
  onSelect: (filename: string) => void
  onDelete: (filename: string) => void
}

export const VideoCard: React.FC<VideoCardProps> = ({ video, selected, onSelect, onDelete }) => {
  const thumbUrl = video.filename
    ? videoApi.getThumbnailUrl(video.filename)
    : null
  const variant = STATUS_VARIANT[video.status] ?? 'secondary'

  return (
    <div
      className={`relative rounded-lg border-2 overflow-hidden group cursor-pointer transition-all
        ${selected ? 'border-primary shadow-md' : 'border-transparent hover:border-muted-foreground/30'}`}
      onClick={() => video.filename && onSelect(video.filename)}
    >
      {/* Thumbnail / placeholder */}
      <div className="aspect-video bg-muted relative">
        {thumbUrl ? (
          <img
            src={thumbUrl}
            alt={video.filename}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Film className="w-8 h-8 text-muted-foreground opacity-50" />
          </div>
        )}

        {/* Checkbox */}
        <div className="absolute top-2 left-2" onClick={e => e.stopPropagation()}>
          <Checkbox
            checked={selected}
            onCheckedChange={() => video.filename && onSelect(video.filename)}
          />
        </div>

        {/* Status badge */}
        <div className="absolute top-2 right-2">
          <Badge variant={variant} className="text-xs capitalize">{video.status}</Badge>
        </div>
      </div>

      {/* Footer */}
      <div className="p-2 flex items-center justify-between gap-1">
        <p className="text-xs text-muted-foreground truncate">
          {video.filename ?? `ID ${video.id}`}
        </p>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 w-6 p-0 text-destructive hover:text-destructive shrink-0"
          onClick={e => {
            e.stopPropagation()
            if (video.filename) onDelete(video.filename)
          }}
        >
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  )
}
