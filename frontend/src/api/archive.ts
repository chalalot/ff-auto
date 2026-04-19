import { apiClient } from '@/lib/api-client'
import type { ArchiveListResponse, ImageMetadata } from '@/types'

export const archiveApi = {
  list: (params: { server?: string; page?: number; per_page?: number }) =>
    apiClient
      .get<ArchiveListResponse>('/archive/list', { params })
      .then((r) => r.data),

  servers: () =>
    apiClient
      .get<{ servers: string[] }>('/archive/servers')
      .then((r) => r.data),

  getThumbnailUrl: (server: string, filename: string) =>
    `/api/archive/thumbnail?server=${encodeURIComponent(server)}&filename=${encodeURIComponent(filename)}`,

  getMetadata: (server: string, filename: string) =>
    apiClient
      .get<ImageMetadata>('/archive/metadata', { params: { server, filename } })
      .then((r) => r.data),

  getRefImageUrl: (server: string, filename: string) =>
    `/api/archive/ref-image?server=${encodeURIComponent(server)}&filename=${encodeURIComponent(filename)}`,

  getImageUrl: (server: string, filename: string) =>
    `/api/archive/image?server=${encodeURIComponent(server)}&filename=${encodeURIComponent(filename)}`,
}
