import { apiClient } from '@/lib/api-client'
import type { WorkflowGraph, WorkflowSummary } from '@/types'

/**
 * Management of the ComfyUI workflow JSON files in the backend's workflows dir.
 *
 * Distinct from `workspaceApi.getWorkflows()`, which lists bare filenames for
 * the generation selector. These endpoints read and write the graphs themselves.
 * Every mutation returns the resulting `name` because the server may adjust it
 * (a `.json` suffix is added, and imports/duplicates side-step collisions).
 */
export const workflowsApi = {
  list: () =>
    apiClient.get<WorkflowSummary[]>('/workspace/workflows/library').then(r => r.data),

  /**
   * Opens a workflow for editing. `raw` is always the file text — a file that
   * doesn't parse comes back with `graph: null` and an `error`, so the JSON
   * editor can be used to repair it instead of the request failing.
   */
  getGraph: (name: string) =>
    apiClient
      .get<{ name: string; raw: string; graph: WorkflowGraph | null; error: string | null }>(
        `/workspace/workflows/${encodeURIComponent(name)}/graph`,
      )
      .then(r => r.data),

  create: (name: string, graph?: WorkflowGraph) =>
    apiClient
      .post<{ name: string }>('/workspace/workflows', { name, graph })
      .then(r => r.data),

  save: (name: string, graph: WorkflowGraph) =>
    apiClient
      .put<{ name: string }>(`/workspace/workflows/${encodeURIComponent(name)}`, { graph })
      .then(r => r.data),

  duplicate: (name: string, newName?: string) =>
    apiClient
      .post<{ name: string }>(
        `/workspace/workflows/${encodeURIComponent(name)}/duplicate`,
        { new_name: newName ?? null },
      )
      .then(r => r.data),

  rename: (name: string, newName: string) =>
    apiClient
      .post<{ name: string }>(
        `/workspace/workflows/${encodeURIComponent(name)}/rename`,
        { new_name: newName },
      )
      .then(r => r.data),

  remove: (name: string) =>
    apiClient
      .delete<{ name: string }>(`/workspace/workflows/${encodeURIComponent(name)}`)
      .then(r => r.data),

  import: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    // Content-Type must be unset so the browser adds the multipart boundary.
    return apiClient
      .post<{ name: string }>('/workspace/workflows/import', form, {
        headers: { 'Content-Type': undefined },
      })
      .then(r => r.data)
  },
}
