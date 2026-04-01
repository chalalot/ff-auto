import React from 'react'
import { Button } from '@/components/ui/button'
import { ChevronUp, ChevronDown, Trash2, Film } from 'lucide-react'
import { videoApi } from '@/api/video'

interface TimelineEditorProps {
  timeline: string[]
  onReorder: (newOrder: string[]) => void
  onRemove: (filename: string) => void
}

export const TimelineEditor: React.FC<TimelineEditorProps> = ({
  timeline,
  onReorder,
  onRemove,
}) => {
  const move = (idx: number, direction: 'up' | 'down') => {
    const next = [...timeline]
    const target = direction === 'up' ? idx - 1 : idx + 1
    if (target < 0 || target >= next.length) return
    ;[next[idx], next[target]] = [next[target], next[idx]]
    onReorder(next)
  }

  if (timeline.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-muted-foreground border rounded-lg border-dashed">
        <Film className="w-8 h-8 mb-2 opacity-40" />
        <p className="text-sm">No clips in timeline. Add videos from the library.</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">Timeline ({timeline.length} clips)</p>
      {timeline.map((filename, idx) => {
        const thumbUrl = videoApi.getThumbnailUrl(filename)
        return (
          <div
            key={`${filename}-${idx}`}
            className="flex items-center gap-3 rounded-md border px-3 py-2"
          >
            <span className="text-xs text-muted-foreground w-5 shrink-0 text-center">
              {idx + 1}
            </span>
            <img
              src={thumbUrl}
              alt={filename}
              className="w-16 h-9 rounded object-cover shrink-0"
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
            />
            <p className="text-sm flex-1 truncate">{filename}</p>
            <div className="flex gap-1 shrink-0">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0"
                disabled={idx === 0}
                onClick={() => move(idx, 'up')}
              >
                <ChevronUp className="w-3.5 h-3.5" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0"
                disabled={idx === timeline.length - 1}
                onClick={() => move(idx, 'down')}
              >
                <ChevronDown className="w-3.5 h-3.5" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                onClick={() => onRemove(filename)}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
