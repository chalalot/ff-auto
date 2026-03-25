import { useQuery } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'

export const useTaskProgress = (taskId: string | null) => {
  return useQuery({
    queryKey: ['tasks', taskId],
    queryFn: () => workspaceApi.getTaskStatus(taskId!),
    enabled: !!taskId,
    refetchInterval: (query) => {
      const state = query.state.data?.state
      if (state === 'SUCCESS' || state === 'FAILURE') return false
      return 1000
    },
  })
}
