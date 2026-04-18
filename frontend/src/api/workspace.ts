import { apiClient } from '@/lib/api-client'
import type { InputImage, RefImage, ProcessImageConfig, TaskStatusResponse, ExecutionRecord, CaptionExportEntry } from '@/types'

export const workspaceApi = {
  getInputImages: () =>
    apiClient.get<InputImage[]>('/workspace/input-images').then(r => r.data),

  getThumbnailUrl: (filename: string) =>
    `/api/workspace/input-images/${filename}/thumbnail`,

  process: (config: ProcessImageConfig & { skip_prepare?: boolean }) =>
    apiClient.post<{ task_id: string }>('/workspace/process', config).then(r => r.data),

  processBatch: (imagePaths: string[], sharedConfig: Omit<ProcessImageConfig, 'image_path'> & { skip_prepare?: boolean }) =>
    apiClient.post<{ task_ids: string[] }>('/workspace/process-batch', {
      image_paths: imagePaths,
      ...sharedConfig,
    }).then(r => r.data),

  getTaskStatus: (taskId: string) =>
    apiClient.get<TaskStatusResponse>(`/workspace/task/${taskId}/status`).then(r => r.data),

  getExecutions: (params?: { limit?: number; status?: string }) =>
    apiClient.get<ExecutionRecord[]>('/workspace/executions', { params }).then(r => r.data),

  // Ref image library
  getRefImages: () =>
    apiClient.get<RefImage[]>('/workspace/ref-images').then(r => r.data),

  getRefImageThumbnailUrl: (filename: string) =>
    `/api/workspace/ref-images/${encodeURIComponent(filename)}/thumbnail`,

  getRefImageUrl: (filename: string) =>
    `/api/workspace/ref-images/${encodeURIComponent(filename)}`,

  uploadRefImages: (files: File[]) => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    // Must unset Content-Type so the browser sets multipart/form-data with boundary
    return apiClient.post<RefImage[]>('/workspace/ref-images/upload', form, {
      headers: { 'Content-Type': undefined },
    }).then(r => r.data)
  },

  deleteRefImage: (filename: string) =>
    apiClient.delete(`/workspace/ref-images/${encodeURIComponent(filename)}`).then(r => r.data),

  // Caption Export
  captionExportUpload: (files: File[]) => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    return apiClient.post<{ entries: CaptionExportEntry[] }>(
      '/workspace/caption-export/upload',
      form,
      { headers: { 'Content-Type': undefined } },
    ).then(r => r.data)
  },

  captionExportStart: (payload: {
    image_entries: CaptionExportEntry[]
    persona: string
    vision_model: string
    workflow_type: string
  }) =>
    apiClient.post<{ task_id: string }>('/workspace/caption-export/start', payload).then(r => r.data),

  getCaptionExportDownloadUrl: (taskId: string) =>
    `/api/workspace/caption-export/${taskId}/download`,

  // Google Drive integration
  captionExportGdriveFetch: (payload: { folder_url: string; max_dimension: number }) =>
    apiClient.post<{ entries: CaptionExportEntry[] }>(
      '/workspace/caption-export/gdrive/fetch',
      payload,
    ).then(r => r.data),

  captionExportGdriveUploadZip: (payload: { task_id: string; folder_url: string }) =>
    apiClient.post<{ file_id: string; filename: string }>(
      '/workspace/caption-export/gdrive/upload-zip',
      payload,
    ).then(r => r.data),
}
