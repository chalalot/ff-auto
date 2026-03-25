import { apiClient } from '@/lib/api-client'
import type { GalleryResponse, ImageMetadata, GalleryStats } from '@/types'

export type GalleryStatus = 'pending' | 'approved' | 'disapproved'

export const galleryApi = {
  getImages: (params: {
    status: GalleryStatus
    page?: number
    per_page?: number
    group_by?: string
    sort?: string
  }) =>
    apiClient.get<GalleryResponse>('/gallery/images', { params }).then(r => r.data),

  getThumbnailUrl: (filename: string, status: GalleryStatus) =>
    `/api/gallery/images/${encodeURIComponent(filename)}/thumbnail?status=${status}`,

  getMetadata: (filename: string, status: GalleryStatus) =>
    apiClient.get<ImageMetadata>(`/gallery/images/${encodeURIComponent(filename)}/metadata`, {
      params: { status }
    }).then(r => r.data),

  getDownloadUrl: (filename: string) =>
    `/api/gallery/download/${encodeURIComponent(filename)}`,

  approve: (filenames: string[], renameMap?: Record<string, string>) =>
    apiClient.post('/gallery/approve', { filenames, rename_map: renameMap || {} }).then(r => r.data),

  disapprove: (filenames: string[]) =>
    apiClient.post('/gallery/disapprove', { filenames }).then(r => r.data),

  undo: (filenames: string[], fromStatus: 'approved' | 'disapproved') =>
    apiClient.post('/gallery/undo', { filenames, from_status: fromStatus }).then(r => r.data),

  getStats: () =>
    apiClient.get<GalleryStats>('/gallery/stats').then(r => r.data),

  downloadZip: (filenames: string[]) =>
    apiClient.post('/gallery/download-zip', { filenames }, { responseType: 'blob' }).then(r => r.data),

  getNotes: () =>
    apiClient.get<Record<string, string>>('/gallery/notes').then(r => r.data),

  saveNote: (date: string, note: string) =>
    apiClient.put('/gallery/notes', { date, note }).then(r => r.data),
}
