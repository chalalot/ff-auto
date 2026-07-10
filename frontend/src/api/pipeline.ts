import { apiClient } from '@/lib/api-client'
import type { PipelineRunSummary, PipelineRunTrace } from '@/types/pipeline'

export const pipelineApi = {
  listRuns: (params?: { limit?: number; project_id?: string }) =>
    apiClient.get<PipelineRunSummary[]>('/pipeline-runs', { params }).then(r => r.data),
  getRun: (runId: string) =>
    apiClient.get<PipelineRunTrace>(`/pipeline-runs/${encodeURIComponent(runId)}`).then(r => r.data),
}
