import { apiClient } from '@/lib/api-client'
import type { AnalysisResponse, AnalysisStatusFilter, EvaluatedFilter } from '@/types/analysis'

export const analysisApi = {
  list: (params: {
    status?: AnalysisStatusFilter
    evaluated?: EvaluatedFilter
    page?: number
    per_page?: number
    project_id?: string
  }) =>
    apiClient.get<AnalysisResponse>('/analysis', { params }).then(r => r.data),
}
