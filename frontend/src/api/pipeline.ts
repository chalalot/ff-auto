import { apiClient } from '@/lib/api-client'
import type { PipelineRunTrace } from '@/types/pipeline'

export const pipelineApi = {
  getRun: (runId: string) =>
    apiClient.get<PipelineRunTrace>(`/pipeline-runs/${encodeURIComponent(runId)}`).then(r => r.data),
}
