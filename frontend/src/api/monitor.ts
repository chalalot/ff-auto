import { apiClient } from '@/lib/api-client'
import type { SystemHealth } from '@/types'

export const monitorApi = {
  getHealth: () =>
    apiClient.get<SystemHealth>('/monitor/health').then(r => r.data),

  getProcesses: () =>
    apiClient.get('/monitor/processes').then(r => r.data),

  getDbStats: () =>
    apiClient.get('/monitor/db-stats').then(r => r.data),

  getFilesystem: () =>
    apiClient.get('/monitor/filesystem').then(r => r.data),
}
