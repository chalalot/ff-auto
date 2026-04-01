import React from 'react'
import { Film } from 'lucide-react'

interface VideoPreviewProps {
  src: string
  poster?: string
}

export const VideoPreview: React.FC<VideoPreviewProps> = ({ src, poster }) => {
  if (!src) {
    return (
      <div className="flex flex-col items-center justify-center bg-muted rounded-lg aspect-video text-muted-foreground">
        <Film className="w-10 h-10 mb-2 opacity-50" />
        <p className="text-sm">No video available</p>
      </div>
    )
  }

  return (
    <video
      src={src}
      poster={poster}
      controls
      className="w-full rounded-lg aspect-video bg-black object-contain"
      preload="metadata"
    />
  )
}
