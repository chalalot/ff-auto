import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { uploadsApi } from '@/api/uploads'

export const AssetsPanel: React.FC<{ projectId: string }> = ({ projectId }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['uploads', projectId],
    queryFn: () => uploadsApi.list({ project_id: projectId, per_page: 200 }),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }
  const items = data?.items ?? []
  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-12">
        No uploads in this project yet. Files uploaded from the Workspace while
        this project is active will appear here.
      </p>
    )
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3 p-4">
      {items.map(u => (
        <figure key={u.id} className="space-y-1">
          <img
            src={uploadsApi.getThumbnailUrl(u.id)}
            alt={u.filename}
            className="aspect-square w-full rounded object-cover bg-muted"
            onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden' }}
          />
          <figcaption className="truncate text-[11px] text-muted-foreground">
            <span className="mr-1 rounded bg-muted px-1 font-mono text-[10px]">{u.kind}</span>
            {u.filename}
          </figcaption>
        </figure>
      ))}
    </div>
  )
}
