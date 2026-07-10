import { useQuery } from '@tanstack/react-query'
import { pipelineApi } from '@/api/pipeline'
import type { PipelineRunStatus } from '@/types/pipeline'

export const pipelineRunRefetchInterval = (status: PipelineRunStatus | undefined) =>
  status === 'queued' || status === 'running' ? 1500 : false

export const usePipelineRun = (runId: string) => {
  const query = useQuery({
    queryKey: ['pipeline-run', runId],
    queryFn: () => pipelineApi.getRun(runId),
    enabled: Boolean(runId),
    refetchInterval: query => pipelineRunRefetchInterval(query.state.data?.status),
  })

  return {
    ...query,
    refreshError: query.error,
  }
}
