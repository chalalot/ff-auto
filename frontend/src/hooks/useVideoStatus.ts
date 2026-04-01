import { useQuery } from '@tanstack/react-query'
import { videoApi } from '@/api/video'

export function useVideoStatus(taskId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['videoStatus', taskId],
    queryFn: () => videoApi.getStatus(taskId!),
    enabled: !!taskId && enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'succeed' || status === 'failed') return false
      return 5000
    },
  })
}
