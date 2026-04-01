import React, { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

interface AudioTrimmerProps {
  file: File | null
}

export const AudioTrimmer: React.FC<AudioTrimmerProps> = ({ file }) => {
  const [startTime, setStartTime] = useState(0)
  const [endTime, setEndTime] = useState(0)

  if (!file) {
    return (
      <p className="text-sm text-muted-foreground">Upload an audio file to enable trimming.</p>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-sm font-medium">Audio Trimmer</p>
      <p className="text-xs text-muted-foreground">
        File: {file.name}
      </p>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Start Time (seconds)</Label>
          <Input
            type="number"
            min={0}
            step={0.1}
            value={startTime}
            onChange={e => setStartTime(Number(e.target.value))}
          />
        </div>
        <div className="space-y-1.5">
          <Label>End Time (seconds)</Label>
          <Input
            type="number"
            min={0}
            step={0.1}
            value={endTime}
            onChange={e => setEndTime(Number(e.target.value))}
          />
        </div>
      </div>

      <Separator />

      <p className="text-xs text-muted-foreground italic">
        Note: Actual audio trimming will be applied server-side when integrated with the backend
        audio pipeline. This UI captures trim points for future use.
      </p>
    </div>
  )
}
