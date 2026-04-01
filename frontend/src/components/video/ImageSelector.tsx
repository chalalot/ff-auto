import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { galleryApi, type GalleryStatus } from '@/api/gallery'
import { Loader2, Image as ImageIcon, CheckCircle } from 'lucide-react'
import type { GalleryResponse } from '@/types'

interface ImageSelectorProps {
  selected: string[]
  onToggle: (path: string) => void
}

const STATUS_TABS: { label: string; value: GalleryStatus }[] = [
  { label: 'Pending', value: 'pending' },
  { label: 'Approved', value: 'approved' },
]

export const ImageSelector: React.FC<ImageSelectorProps> = ({ selected, onToggle }) => {
  const [status, setStatus] = useState<GalleryStatus>('pending')

  const { data, isLoading } = useQuery<GalleryResponse>({
    queryKey: ['galleryImages', status],
    queryFn: () => galleryApi.getImages({ status, per_page: 100 }),
  })

  const images = data?.items ?? []

  return (
    <div className="space-y-2">
      {/* Status tabs */}
      <div className="flex gap-1">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => setStatus(tab.value)}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
              status === tab.value
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-accent'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : images.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-32 text-muted-foreground">
          <ImageIcon className="w-8 h-8 mb-2 opacity-50" />
          <p className="text-sm">No {status} images in gallery</p>
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-2 max-h-64 overflow-y-auto pr-1">
          {images.map(img => {
            const isSelected = selected.includes(img.path)
            const thumbUrl = galleryApi.getThumbnailUrl(img.filename, status)
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
      )}
    </div>
  )
}
