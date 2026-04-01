import { useQuery } from '@tanstack/react-query'
import { videoApi } from '@/api/video'
import type { VideoBackend } from '@/types/video'

export function useVideoStatus(taskId: string | null, backend: VideoBackend = 'api', enabled = true) {
  return useQuery({
    queryKey: ['videoStatus', taskId, backend],
    queryFn: () =>
      backend === 'comfy'
        ? videoApi.getComfyStatus(taskId!)
        : videoApi.getStatus(taskId!),
    enabled: !!taskId && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'completed' || status === 'succeed' || status === 'failed') return false
      return 5000
    },
  })
}
