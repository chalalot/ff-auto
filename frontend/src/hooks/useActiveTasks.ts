import { useQuery } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'

export const useActiveTasks = () => {
  return useQuery({
    queryKey: ['workspace', 'active-tasks'],
    queryFn: workspaceApi.getActiveTasks,
    refetchInterval: 5000,
  })
}
