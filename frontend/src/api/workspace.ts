import { apiClient } from '@/lib/api-client'
import type { InputImage, RefImage, ProcessImageConfig, TaskStatusResponse, ExecutionRecord, ActiveTask, CaptionExportEntry } from '@/types'

export const workspaceApi = {
  getInputImages: () =>
    apiClient.get<InputImage[]>('/workspace/input-images').then(r => r.data),

  getImagePipelines: () =>
    apiClient.get<string[]>('/workspace/image-pipelines').then(r => r.data),

  getPipelines: () =>
    apiClient.get<import('@/types').PipelineInfo[]>('/workspace/pipelines').then(r => r.data),

  getPipelineParameters: (pipelineType: string) =>
    apiClient
      .get<import('@/types').WorkflowParameters>(
        `/workspace/pipelines/${encodeURIComponent(pipelineType)}/parameters`,
      )
      .then(r => r.data),

  getWorkflows: () =>
    apiClient.get<string[]>('/workspace/workflows').then(r => r.data),

  getWorkflowParameters: (workflowName: string) =>
    apiClient
      .get<import('@/types').WorkflowParameters>(
        `/workspace/workflows/${encodeURIComponent(workflowName)}/parameters`,
      )
      .then(r => r.data),

  getThumbnailUrl: (filename: string) =>
    `/api/workspace/input-images/${filename}/thumbnail`,

  process: (config: ProcessImageConfig & { skip_prepare?: boolean }) =>
    apiClient.post<{ task_id: string; run_id?: string | null }>('/workspace/process', config).then(r => r.data),

  processBatch: (imagePaths: string[], sharedConfig: Omit<ProcessImageConfig, 'image_path'> & { skip_prepare?: boolean }) =>
    apiClient.post<{ task_ids: string[]; run_ids: Array<string | null> }>('/workspace/process-batch', {
      image_paths: imagePaths,
      ...sharedConfig,
    }).then(r => r.data),

  // Direct ComfyUI submission — image → LoadImage, optional prompt → CLIPTextEncode.
  runDirect: (payload: {
    image_paths: string[]
    workflow_name: string
    workflow_type: string
    prompt?: string
    workflow_overrides?: Record<string, Record<string, unknown>>
  }) =>
    apiClient.post<{ task_ids: string[]; run_ids: Array<string | null> }>(
      '/workspace/run-direct',
      payload,
    ).then(r => r.data),

  getTaskStatus: (taskId: string) =>
    apiClient.get<TaskStatusResponse>(`/workspace/task/${taskId}/status`).then(r => r.data),

  getActiveTasks: () =>
    apiClient.get<ActiveTask[]>('/workspace/active-tasks').then(r => r.data),

  // Clears a stopped task from the shared list. 409 if it is still working.
  dismissActiveTask: (taskId: string) =>
    apiClient.delete(`/workspace/active-tasks/${taskId}`).then(r => r.data),

  getExecutions: (params?: { limit?: number; status?: string; project_id?: string }) =>
    apiClient.get<ExecutionRecord[]>('/workspace/executions', { params }).then(r => r.data),

  // Ref image library
  getRefImages: (params?: { project_id?: string }) =>
    apiClient.get<RefImage[]>('/workspace/ref-images', { params }).then(r => r.data),

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

  // Server-side download for images dragged in from other web pages — the
  // backend fetches the URL (client-side fetch is blocked by CORS) and relays
  // the bytes; the Blob's type carries the resolved content type.
  fetchImageFromUrl: async (url: string): Promise<Blob> => {
    try {
      const r = await apiClient.post('/workspace/fetch-image', { url }, { responseType: 'blob' })
      return r.data as Blob
    } catch (err) {
      // With responseType 'blob' the error body is a Blob; surface the JSON detail.
      const body = (err as { response?: { data?: unknown } })?.response?.data
      if (body instanceof Blob) {
        const text = await body.text().catch(() => '')
        let detail: string | undefined
        try { detail = (JSON.parse(text) as { detail?: string }).detail } catch { /* not JSON */ }
        if (detail) throw new Error(detail)
      }
      throw err
    }
  },

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
  captionExportUploadOne: (file: File) => {
    const form = new FormData()
    form.append('files', file)
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

  captionExportGdriveUploadZip: (taskId: string) =>
    apiClient.post<{ file_id: string; filename: string; public_url: string }>(
      '/workspace/caption-export/gdrive/upload-zip',
      { task_id: taskId },
    ).then(r => r.data),

  // RunPod LoRA training
  runpodJobs: () =>
    apiClient.get<Array<{
      job_id: string
      endpoint_id: string
      lora_name: string
      submitted_at: string
      job_input: Record<string, unknown>
      status: string | null
      output: Record<string, unknown> | null
    }>>('/workspace/caption-export/runpod/jobs').then(r => r.data),

  runpodSubmit: (payload: {
    job_input: {
      dataset_source: string
      lora_name: string
      steps: number
      save_every: number
      sample_every: number
      sample_prompts: string[]
    }
    endpoint_id?: string
  }) =>
    apiClient.post<{ job_id: string; endpoint_id: string }>(
      '/workspace/caption-export/runpod/submit',
      payload,
    ).then(r => r.data),

  runpodCancel: (jobId: string, endpointId?: string) =>
    apiClient.post<{ job_id: string; status: string }>(
      `/workspace/caption-export/runpod/cancel/${jobId}`,
      null,
      { params: endpointId ? { endpoint_id: endpointId } : undefined }
    ).then(r => r.data),

  runpodDeleteJob: (jobId: string) =>
    apiClient.delete(`/workspace/caption-export/runpod/jobs/${jobId}`).then(r => r.data),

  runpodStatus: (jobId: string, endpointId?: string) =>
    apiClient.get<{ id: string; status: string; output?: Record<string, unknown> | null }>(
      `/workspace/caption-export/runpod/status/${jobId}`,
      { params: endpointId ? { endpoint_id: endpointId } : undefined },
    ).then(r => r.data),

  runpodUploadToHF: (payload: { file_url: string; lora_name: string }) =>
    apiClient.post<{ repo_id: string; filename: string; url: string }>(
      '/workspace/caption-export/runpod/upload-to-hf',
      payload,
    ).then(r => r.data),

  captionExportManualToDrive: (payload: {
    entries: CaptionExportEntry[]
    captions: Record<string, string>
  }) =>
    apiClient.post<{ file_id: string; filename: string; folder_id: string; public_url: string }>(
      '/workspace/caption-export/manual/export-to-drive',
      payload,
    ).then(r => r.data),

  captionExportHistory: () =>
    apiClient.get<Array<{
      id: number
      file_id: string
      filename: string
      public_url: string
      image_count: number
      exported_at: string
    }>>('/workspace/caption-export/manual/exports').then(r => r.data),

  getPersonaInstructions: (personaName: string) =>
    apiClient.get<{
      agent_system: string
      identity_lock: string
    }>(`/workspace/persona-instructions/${encodeURIComponent(personaName)}`).then(r => r.data),
}
