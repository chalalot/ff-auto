import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2, Merge } from 'lucide-react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { videoApi } from '@/api/video'

const TRANSITION_TYPES = ['Crossfade', 'Fade to Black', 'Simple Cut']

interface MergeControlsProps {
  filenames: string[]
  onMergeComplete: (outputFilename: string) => void
}

export const MergeControls: React.FC<MergeControlsProps> = ({ filenames, onMergeComplete }) => {
  const [transitionType, setTransitionType] = useState('Crossfade')
  const [transitionDuration, setTransitionDuration] = useState(0.5)
  const [mergeTaskId, setMergeTaskId] = useState<string | null>(null)

  const mergeMutation = useMutation({
    mutationFn: () =>
      videoApi.mergeVideos({
        filenames,
        transition_type: transitionType,
        transition_duration: transitionDuration,
      }),
    onSuccess: data => setMergeTaskId(data.task_id),
  })

  const { data: statusData } = useQuery({
    queryKey: ['mergeStatus', mergeTaskId],
    queryFn: () => videoApi.getMergeStatus(mergeTaskId!),
    enabled: !!mergeTaskId,
    refetchInterval: query => {
      const state = query.state.data?.state
      if (state === 'SUCCESS' || state === 'FAILURE') return false
      return 2000
    },
  })

  React.useEffect(() => {
    if (statusData?.state === 'SUCCESS' && statusData.result?.output_filename) {
      onMergeComplete(statusData.result.output_filename)
    }
  }, [statusData, onMergeComplete])

  const isMerging =
    mergeTaskId !== null &&
    statusData?.state !== 'SUCCESS' &&
    statusData?.state !== 'FAILURE'

  const progress = statusData?.progress ?? 0

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Transition</Label>
          <Select value={transitionType} onValueChange={setTransitionType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TRANSITION_TYPES.map(t => (
                <SelectItem key={t} value={t}>{t}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label>Duration</Label>
            <span className="text-sm text-muted-foreground">{transitionDuration.toFixed(1)}s</span>
          </div>
          <Slider
            min={0.1}
            max={2.0}
            step={0.1}
            value={[transitionDuration]}
            onValueChange={([v]) => setTransitionDuration(v)}
            disabled={transitionType === 'Simple Cut'}
          />
        </div>
      </div>

      <Button
        onClick={() => mergeMutation.mutate()}
        disabled={filenames.length < 2 || mergeMutation.isPending || isMerging}
        className="w-full"
      >
        {mergeMutation.isPending || isMerging
          ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Merging...</>
          : <><Merge className="w-4 h-4 mr-2" />Merge {filenames.length} Clips</>
        }
      </Button>

      {filenames.length < 2 && (
        <p className="text-xs text-muted-foreground text-center">
          Add at least 2 clips to the timeline to merge.
        </p>
      )}

      {isMerging && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Merging videos...</span>
            <span>{progress}%</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>
      )}

      {statusData?.state === 'SUCCESS' && statusData.result?.output_filename && (
        <div className="rounded-md bg-muted/50 p-3 text-sm">
          Merge complete:
          <a
            href={videoApi.getVideoUrl(statusData.result.output_filename)}
            target="_blank"
            rel="noreferrer"
            className="ml-1 text-primary hover:underline"
          >
            {statusData.result.output_filename}
          </a>
        </div>
      )}

      {statusData?.state === 'FAILURE' && (
        <p className="text-sm text-destructive">Merge failed. Please try again.</p>
      )}
    </div>
  )
}
