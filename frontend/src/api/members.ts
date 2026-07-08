import { apiClient } from '@/lib/api-client'
import type { Member } from '@/types/project'

export const membersApi = {
  list: () => apiClient.get<Member[]>('/members').then(r => r.data),
  create: (name: string) =>
    apiClient.post<Member>('/members', { name }).then(r => r.data),
}
