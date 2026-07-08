import { apiClient } from '@/lib/api-client'
import type { Project } from '@/types/project'

export const projectsApi = {
  list: (includeArchived = false) =>
    apiClient
      .get<Project[]>('/projects', { params: { include_archived: includeArchived } })
      .then(r => r.data),
  create: (name: string, description?: string) =>
    apiClient.post<Project>('/projects', { name, description }).then(r => r.data),
  patch: (id: string, body: { name?: string; description?: string; archived?: boolean }) =>
    apiClient.patch<Project>(`/projects/${id}`, body).then(r => r.data),
  assign: (id: string, table: string, ids: string[]) =>
    apiClient
      .post<{ updated: number }>(`/projects/${id}/assign`, { table, ids })
      .then(r => r.data),
}
