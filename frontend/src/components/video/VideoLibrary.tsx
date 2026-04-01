import React, { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Loader2, Upload, ChevronLeft, ChevronRight, Film } from 'lucide-react'
import { VideoCard } from './VideoCard'
import { VideoPlayerModal } from './VideoPlayerModal'
import { useVideoList } from '@/hooks/useVideoLibrary'
import { videoApi } from '@/api/video'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { VideoItem } from '@/types/video'

const PER_PAGE = 20

export const VideoLibrary: React.FC = () => {
  const [page, setPage] = useState(1)
  const [selectedFilenames, setSelectedFilenames] = useState<Set<string>>(new Set())
  const [activeVideo, setActiveVideo] = useState<VideoItem | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const { data, isLoading, refetch } = useVideoList(page, PER_PAGE)

  const uploadMutation = useMutation({
    mutationFn: (file: File) => videoApi.uploadVideo(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['videos'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (filename: string) => videoApi.deleteVideo(filename),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['videos'] }),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadMutation.mutate(file)
    e.target.value = ''
  }

  const handleSelect = (filename: string) => {
    const video = data?.items.find(v => v.filename === filename)
    if (video) setActiveVideo(video)
  }

  const handleDelete = (filename: string) => {
    deleteMutation.mutate(filename)
    setSelectedFilenames(prev => {
      const next = new Set(prev)
      next.delete(filename)
      return next
    })
  }

  const toggleSelect = (filename: string) => {
    setSelectedFilenames(prev => {
      const next = new Set(prev)
      if (next.has(filename)) next.delete(filename)
      else next.add(filename)
      return next
    })
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMutation.isPending}
        >
          {uploadMutation.isPending
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Uploading...</>
            : <><Upload className="w-4 h-4 mr-2" />Upload Video</>
          }
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={handleFileChange}
        />
        <Button size="sm" variant="ghost" onClick={() => void refetch()}>
          Refresh
        </Button>
        {selectedFilenames.size > 0 && (
          <span className="text-sm text-muted-foreground">{selectedFilenames.size} selected</span>
        )}
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
          <Film className="w-12 h-12 mb-3 opacity-40" />
          <p className="text-sm">No videos yet</p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {data.items.map(video => (
            <VideoCard
              key={video.id}
              video={video}
              selected={video.filename ? selectedFilenames.has(video.filename) : false}
              onSelect={handleSelect}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setPage(p => p - 1)}
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {data.pages} ({data.total} total)
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= data.pages}
            onClick={() => setPage(p => p + 1)}
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}

      {/* Player modal */}
      <VideoPlayerModal video={activeVideo} onClose={() => setActiveVideo(null)} />
    </div>
  )
}
