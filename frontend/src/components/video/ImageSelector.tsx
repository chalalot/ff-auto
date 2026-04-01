import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { workspaceApi } from '@/api/workspace'
import { Loader2, Image as ImageIcon, CheckCircle } from 'lucide-react'
import type { RefImage } from '@/types'

interface ImageSelectorProps {
  selected: string[]
  onToggle: (path: string) => void
}

export const ImageSelector: React.FC<ImageSelectorProps> = ({ selected, onToggle }) => {
  const { data: images, isLoading } = useQuery<RefImage[]>({
    queryKey: ['refImages'],
    queryFn: () => apiClient.get<RefImage[]>('/workspace/ref-images').then(r => r.data),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!images || images.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-muted-foreground">
        <ImageIcon className="w-8 h-8 mb-2 opacity-50" />
        <p className="text-sm">No reference images found</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-4 gap-2 max-h-64 overflow-y-auto pr-1">
      {images.map(img => {
        const isSelected = selected.includes(img.path)
        const thumbUrl = workspaceApi.getRefImageThumbnailUrl(img.filename)
        return (
          <button
            key={img.filename}
            onClick={() => onToggle(img.path)}
            className={`relative rounded-md overflow-hidden border-2 aspect-square transition-all focus:outline-none
              ${isSelected ? 'border-primary shadow-md' : 'border-transparent hover:border-muted-foreground/40'}`}
          >
            <img
              src={thumbUrl}
              alt={img.filename}
              className="w-full h-full object-cover"
              loading="lazy"
            />
            {isSelected && (
              <div className="absolute inset-0 bg-primary/20 flex items-center justify-center">
                <CheckCircle className="w-6 h-6 text-primary drop-shadow" />
              </div>
            )}
            <div className="absolute bottom-0 left-0 right-0 bg-black/60 px-1 py-0.5">
              <p className="text-white text-[10px] truncate">{img.filename}</p>
            </div>
          </button>
        )
      })}
    </div>
  )
}
