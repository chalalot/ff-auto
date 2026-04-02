import React, { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { galleryApi, type GalleryStatus } from '@/api/gallery'
import { workspaceApi } from '@/api/workspace'
import { Loader2, Image as ImageIcon, CheckCircle, Upload } from 'lucide-react'
import type { GalleryResponse, RefImage } from '@/types'

interface ImageSelectorProps {
  selected: string[]
  onToggle: (path: string) => void
}

type TabStatus = GalleryStatus | 'uploads'

const STATUS_TABS: { label: string; value: TabStatus }[] = [
  { label: 'Pending', value: 'pending' },
  { label: 'Approved', value: 'approved' },
  { label: 'Uploads', value: 'uploads' },
]

export const ImageSelector: React.FC<ImageSelectorProps> = ({ selected, onToggle }) => {
  const [status, setStatus] = useState<TabStatus>('pending')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  // Gallery query
  const { data: galleryData, isLoading: isLoadingGallery } = useQuery<GalleryResponse>({
    queryKey: ['galleryImages', status],
    queryFn: () => galleryApi.getImages({ status: status as GalleryStatus, per_page: 100 }),
    enabled: status !== 'uploads',
  })

  // Uploads query
  const { data: uploadsData, isLoading: isLoadingUploads } = useQuery<RefImage[]>({
    queryKey: ['refImages'],
    queryFn: workspaceApi.getRefImages,
    enabled: status === 'uploads',
  })

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => workspaceApi.uploadRefImages(files),
    onSuccess: (newImages) => {
      queryClient.invalidateQueries({ queryKey: ['refImages'] })
      // Auto-select newly uploaded images
      newImages.forEach(img => {
        if (!selected.includes(img.path)) {
          onToggle(img.path)
        }
      })
      // Switch to uploads tab to see them
      setStatus('uploads')
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      uploadMutation.mutate(Array.from(e.target.files))
    }
    // Reset the input so the same files can be selected again if needed
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const isLoading = status === 'uploads' ? isLoadingUploads : isLoadingGallery
  
  // Normalize images list
  const images = status === 'uploads' 
    ? (uploadsData ?? [])
    : (galleryData?.items ?? [])

  return (
    <div className="space-y-2">
      {/* Header controls */}
      <div className="flex items-center justify-between">
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

        {/* Upload button */}
        <div>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            className="hidden"
            multiple
            accept="image/*"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50"
          >
            {uploadMutation.isPending ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Upload className="w-3 h-3" />
            )}
            Upload Image
          </button>
        </div>
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
            const thumbUrl = status === 'uploads' 
              ? workspaceApi.getRefImageThumbnailUrl(img.filename)
              : galleryApi.getThumbnailUrl(img.filename, status as GalleryStatus)
              
            return (
              <button
                key={img.path} // Use path as key instead of filename to be safe
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
