import { apiClient } from '@/lib/api-client'
import type { EvaluationListResponse, EvaluationRequest, EvaluationResult } from '@/types/evaluation'

export const evaluationsApi = {
  create: (body: EvaluationRequest) =>
    apiClient.post<EvaluationResult>('/evaluations', body, { timeout: 120000 }).then(r => r.data),

  get: (id: number) =>
    apiClient.get<EvaluationResult>(`/evaluations/${id}`).then(r => r.data),

  list: (params?: { limit?: number; media_path?: string; project_id?: string }) =>
    apiClient.get<EvaluationListResponse>('/evaluations', { params }).then(r => r.data),
}
