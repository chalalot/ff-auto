import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { videoApi } from '@/api/video'
import { Loader2, Music2, FileText } from 'lucide-react'

interface MusicAnalysisResultsProps {
  taskId: string | null
}

export const MusicAnalysisResults: React.FC<MusicAnalysisResultsProps> = ({ taskId }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['musicAnalysis', taskId],
    queryFn: () => videoApi.getMusicAnalysisStatus(taskId!),
    enabled: !!taskId,
    refetchInterval: query => {
      const state = query.state.data?.state
      if (state === 'SUCCESS' || state === 'FAILURE') return false
      return 3000
    },
  })

  if (!taskId) return null

  if (isLoading || (data && data.state !== 'SUCCESS' && data.state !== 'FAILURE')) {
    return (
      <div className="flex items-center gap-2 py-4 text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span className="text-sm">Analyzing music...</span>
      </div>
    )
  }

  if (data?.state === 'FAILURE') {
    return <p className="text-sm text-destructive">Analysis failed. Please try again.</p>
  }

  if (!data?.result) return null

  const { vibe, lyrics, analysis } = data.result

  return (
    <div className="space-y-4">
      {/* Vibe */}
      <div className="rounded-lg border p-4 space-y-2">
        <div className="flex items-center gap-2">
          <Music2 className="w-4 h-4 text-muted-foreground" />
          <p className="text-sm font-medium">Vibe</p>
        </div>
        <p className="text-sm whitespace-pre-wrap">{vibe}</p>
      </div>

      {/* Lyrics */}
      <div className="rounded-lg border p-4 space-y-2">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-muted-foreground" />
          <p className="text-sm font-medium">Lyrics</p>
        </div>
        <p className="text-sm whitespace-pre-wrap">{lyrics}</p>
      </div>

      {/* Analysis */}
      {analysis && (
        <div className="rounded-lg border p-4 space-y-2">
          <p className="text-sm font-medium">Analysis</p>
          <p className="text-sm whitespace-pre-wrap text-muted-foreground">{analysis}</p>
        </div>
      )}
    </div>
  )
}
