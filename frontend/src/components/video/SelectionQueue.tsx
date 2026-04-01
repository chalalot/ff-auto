import React from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Trash2, ChevronUp, ChevronDown } from 'lucide-react'
import { workspaceApi } from '@/api/workspace'

interface QueueItem {
  image_path: string
  prompt?: string
  variation_count: number
}

interface SelectionQueueProps {
  items: QueueItem[]
  onUpdate: (idx: number, update: Partial<{ prompt: string; variation_count: number }>) => void
  onRemove: (idx: number) => void
}

export const SelectionQueue: React.FC<SelectionQueueProps> = ({ items, onUpdate, onRemove }) => {
  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-6">
        No images selected. Pick images from the selector above.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {items.map((item, idx) => {
        const filename = item.image_path.split('/').pop() ?? item.image_path
        const thumbUrl = workspaceApi.getRefImageThumbnailUrl(filename)
        return (
          <div key={`${item.image_path}-${idx}`} className="rounded-lg border p-3 space-y-2">
            <div className="flex gap-3">
              <img
                src={thumbUrl}
                alt={filename}
                className="w-12 h-12 rounded object-cover shrink-0"
                onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{filename}</p>
                <div className="flex items-center gap-2 mt-1">
                  <Label className="text-xs text-muted-foreground shrink-0">Variations</Label>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 w-6 p-0"
                      onClick={() => onUpdate(idx, { variation_count: Math.max(1, item.variation_count - 1) })}
                    >
                      <ChevronDown className="w-3 h-3" />
                    </Button>
                    <span className="text-sm w-4 text-center">{item.variation_count}</span>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 w-6 p-0"
                      onClick={() => onUpdate(idx, { variation_count: Math.min(5, item.variation_count + 1) })}
                    >
                      <ChevronUp className="w-3 h-3" />
                    </Button>
                  </div>
                </div>
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 w-8 p-0 text-destructive hover:text-destructive shrink-0"
                onClick={() => onRemove(idx)}
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
            <Textarea
              placeholder="Prompt for this image (leave blank to auto-generate)..."
              value={item.prompt ?? ''}
              onChange={e => onUpdate(idx, { prompt: e.target.value })}
              className="text-sm min-h-[60px] resize-none"
            />
            {idx < items.length - 1 && <Separator />}
          </div>
        )
      })}
    </div>
  )
}
