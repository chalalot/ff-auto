import { apiClient } from '@/lib/api-client'
import type { UploadListResponse } from '@/types/project'

export const uploadsApi = {
  list: (params: { project_id?: string; page?: number; per_page?: number }) =>
    apiClient.get<UploadListResponse>('/uploads', { params }).then(r => r.data),
  getThumbnailUrl: (id: string) => `/api/uploads/${id}/thumbnail`,
}
