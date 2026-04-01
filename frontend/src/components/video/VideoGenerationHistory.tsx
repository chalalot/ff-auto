import React from 'react'
import { Badge } from '@/components/ui/badge'
import { Loader2, Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useVideoList } from '@/hooks/useVideoLibrary'
import { videoApi } from '@/api/video'
import { formatDistanceToNow } from 'date-fns'
import type { VideoItem } from '@/types/video'

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  processing: 'default',
  succeed: 'outline',
  completed: 'outline',
  failed: 'destructive',
}

const StatusBadge: React.FC<{ status: string }> = ({ status }) => (
  <Badge variant={STATUS_VARIANT[status] ?? 'secondary'} className="text-xs capitalize">
    {status}
  </Badge>
)

const timeAgo = (dateStr: string) => {
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true })
  } catch {
    return dateStr
  }
}

export const VideoGenerationHistory: React.FC = () => {
  const { data, isLoading, refetch } = useVideoList(1, 50)

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-6 text-muted-foreground justify-center">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span className="text-sm">Loading history...</span>
      </div>
    )
  }

  const items: VideoItem[] = data?.items ?? []

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Generation History</p>
        <Button size="sm" variant="ghost" onClick={() => void refetch()}>
          <RefreshCw className="w-3.5 h-3.5 mr-1" />Refresh
        </Button>
      </div>

      {items.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-6">No video generations yet.</p>
      )}

      <div className="rounded-md border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">ID</th>
              <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">Source</th>
              <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">Status</th>
              <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">Created</th>
              <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => {
              const source = item.source_image
                ? item.source_image.split('/').pop()
                : '—'
              const hasVideo =
                (item.status === 'succeed' || item.status === 'completed') && item.filename
              return (
                <tr key={item.id} className={i % 2 === 0 ? '' : 'bg-muted/20'}>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {item.id}
                  </td>
                  <td className="px-3 py-2 max-w-[180px] truncate" title={item.source_image}>
                    {source}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {timeAgo(item.created_at)}
                  </td>
                  <td className="px-3 py-2">
                    {hasVideo && item.filename && (
                      <a
                        href={videoApi.getVideoUrl(item.filename)}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        <Play className="w-3 h-3" />Play
                      </a>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
