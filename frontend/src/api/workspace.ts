import { apiClient } from '@/lib/api-client'
import type { InputImage, ProcessImageConfig, TaskStatusResponse, ExecutionRecord } from '@/types'

export const workspaceApi = {
  getInputImages: () =>
    apiClient.get<InputImage[]>('/workspace/input-images').then(r => r.data),

  getThumbnailUrl: (filename: string) =>
    `/api/workspace/input-images/${filename}/thumbnail`,

  process: (config: ProcessImageConfig) =>
    apiClient.post<{ task_id: string }>('/workspace/process', config).then(r => r.data),

  processBatch: (imagePaths: string[], sharedConfig: Omit<ProcessImageConfig, 'image_path'>) =>
    apiClient.post<{ task_ids: string[] }>('/workspace/process-batch', {
      image_paths: imagePaths,
      ...sharedConfig,
    }).then(r => r.data),

  getTaskStatus: (taskId: string) =>
    apiClient.get<TaskStatusResponse>(`/workspace/task/${taskId}/status`).then(r => r.data),

  getExecutions: (params?: { limit?: number; status?: string }) =>
    apiClient.get<ExecutionRecord[]>('/workspace/executions', { params }).then(r => r.data),
}
