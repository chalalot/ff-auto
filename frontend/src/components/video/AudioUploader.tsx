import React, { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Loader2, Music, Upload } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { videoApi } from '@/api/video'

interface AudioUploaderProps {
  onFileSelected: (file: File) => void
  onUpload: (taskId: string) => void
}

export const AudioUploader: React.FC<AudioUploaderProps> = ({ onFileSelected, onUpload }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const uploadMutation = useMutation({
    mutationFn: (file: File) => videoApi.analyzeMusicFile(file),
    onSuccess: data => onUpload(data.task_id),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      onFileSelected(file)
    }
    e.target.value = ''
  }

  const handleUpload = () => {
    if (selectedFile) uploadMutation.mutate(selectedFile)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          variant="outline"
          onClick={() => fileInputRef.current?.click()}
        >
          <Music className="w-4 h-4 mr-2" />
          Choose Audio File
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="audio/*"
          className="hidden"
          onChange={handleFileChange}
        />
        {selectedFile && (
          <span className="text-sm text-muted-foreground truncate max-w-xs">
            {selectedFile.name}
          </span>
        )}
      </div>

      {selectedFile && (
        <Button
          onClick={handleUpload}
          disabled={uploadMutation.isPending}
        >
          {uploadMutation.isPending
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Analyzing...</>
            : <><Upload className="w-4 h-4 mr-2" />Upload & Analyze</>
          }
        </Button>
      )}

      {uploadMutation.isError && (
        <p className="text-sm text-destructive">Upload failed. Please try again.</p>
      )}

      {uploadMutation.isSuccess && (
        <p className="text-sm text-muted-foreground">
          Analysis started. Results will appear below when ready.
        </p>
      )}
    </div>
  )
}
