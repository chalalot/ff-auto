import { apiClient } from '@/lib/api-client'
import type {
  ReviewCreateResponse,
  ReviewDispatchResponse,
  ReviewItemCreate,
  ReviewListResponse,
  ReviewRequestItem,
  ReviewStatus,
} from '@/types/review'

export const reviewApi = {
  listRequests: (params?: {
    status?: ReviewStatus
    batch_id?: string
    page?: number
    per_page?: number
  }) =>
    apiClient.get<ReviewListResponse>('/review/requests', { params }).then(r => r.data),

  createRequests: (body: { items: ReviewItemCreate[]; batch_id?: string }) =>
    apiClient.post<ReviewCreateResponse>('/review/requests', body).then(r => r.data),

  updateRequest: (id: string, body: { prompt?: string; settings?: Record<string, unknown> }) =>
    apiClient.patch<ReviewRequestItem>(`/review/requests/${id}`, body).then(r => r.data),

  discardRequest: (id: string) =>
    apiClient.delete<ReviewRequestItem>(`/review/requests/${id}`).then(r => r.data),

  dispatch: (ids: string[]) =>
    apiClient.post<ReviewDispatchResponse>('/review/dispatch', { ids }).then(r => r.data),

  getThumbnailUrl: (id: string) => `/api/review/requests/${id}/thumbnail`,
}
