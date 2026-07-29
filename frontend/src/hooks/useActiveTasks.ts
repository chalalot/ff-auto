import { useQuery } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'
import type { ActiveTask } from '@/types'

const TERMINAL_STATES = new Set(['SUCCESS', 'FAILURE', 'REVOKED'])

export const hasActiveWork = (tasks: ActiveTask[] | undefined) =>
  (tasks ?? []).some(t => !TERMINAL_STATES.has(t.state))

// This hook is mounted in Layout, so it polls on every page. Poll fast only
// while a worker is actually busy; back off when idle.
export const useActiveTasks = () => {
  return useQuery({
    queryKey: ['workspace', 'active-tasks'],
    queryFn: workspaceApi.getActiveTasks,
    refetchInterval: query => (hasActiveWork(query.state.data) ? 5000 : 30000),
  })
}
