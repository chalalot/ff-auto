import { apiClient } from '@/lib/api-client'
import type {
  VideoListResponse,
  VideoStatusResponse,
  StoryboardResponse,
  KlingPreset,
  MusicAnalysisResponse,
  KlingSettings,
  VideoBatchRequest,
} from '@/types/video'

export const videoApi = {
  // Storyboard
  generateStoryboard: (body: {
    image_paths: string[]
    vision_model?: string
    persona?: string
    variation_count?: number
  }) =>
    apiClient.post<StoryboardResponse>('/video/storyboard', body).then(r => r.data),

  // Generate
  generate: (body: {
    image_path: string
    prompt?: string
    kling_settings: KlingSettings
    batch_id?: string
  }) =>
    apiClient
      .post<{ task_id: string; batch_id?: string; status: string }>('/video/generate', body)
      .then(r => r.data),

  generateBatch: (body: VideoBatchRequest) =>
    apiClient
      .post<{ batch_id: string; task_ids: string[] }>('/video/generate-batch', body)
      .then(r => r.data),

  // Status
  getStatus: (taskId: string) =>
    apiClient.get<VideoStatusResponse>(`/video/status/${taskId}`).then(r => r.data),

  // List
  listVideos: (params?: { page?: number; per_page?: number }) =>
    apiClient.get<VideoListResponse>('/video/list', { params }).then(r => r.data),

  // File URLs (direct browser URLs)
  getVideoUrl: (filename: string) => `/api/video/${encodeURIComponent(filename)}`,
  getThumbnailUrl: (filename: string) => `/api/video/${encodeURIComponent(filename)}/thumbnail`,

  // Merge
  mergeVideos: (body: {
    filenames: string[]
    transition_type: string
    transition_duration: number
  }) =>
    apiClient
      .post<{ task_id: string; output_filename: string }>('/video/merge', body)
      .then(r => r.data),

  getMergeStatus: (taskId: string) =>
    apiClient
      .get<{ state: string; progress?: number; result?: { output_filename: string } }>(
        `/video/merge/${taskId}/status`
      )
      .then(r => r.data),

  // Upload
  uploadVideo: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post<{ filename: string }>('/video/upload', form, {
        headers: { 'Content-Type': undefined },
      })
      .then(r => r.data)
  },

  // Delete
  deleteVideo: (filename: string) =>
    apiClient.delete(`/video/${encodeURIComponent(filename)}`).then(r => r.data),

  // Music analysis
  analyzeMusicFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post<{ task_id: string }>('/video/music-analysis', form, {
        headers: { 'Content-Type': undefined },
      })
      .then(r => r.data)
  },

  getMusicAnalysisStatus: (taskId: string) =>
    apiClient
      .get<{ state: string; result?: MusicAnalysisResponse }>(`/video/music-analysis/${taskId}/status`)
      .then(r => r.data),

  // Kling presets
  getKlingPresets: () =>
    apiClient.get<KlingPreset[]>('/video/kling-presets').then(r => r.data),

  saveKlingPreset: (preset: KlingPreset) =>
    apiClient.post<KlingPreset>('/video/kling-presets', preset).then(r => r.data),

  deleteKlingPreset: (name: string) =>
    apiClient.delete(`/video/kling-presets/${encodeURIComponent(name)}`).then(r => r.data),
}
