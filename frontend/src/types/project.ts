export interface Member {
  id: string
  name: string
  created_at?: string | null
}

export interface Project {
  id: string
  name: string
  description?: string | null
  owner_member_id?: string | null
  created_at?: string | null
  archived_at?: string | null
  member_ids: string[]
}

export interface UploadItem {
  id: string
  filename: string
  path: string
  kind: 'input' | 'ref'
  project_id?: string | null
  created_by_member_id?: string | null
  created_at?: string | null
}

export interface UploadListResponse {
  items: UploadItem[]
  total: number
  page: number
  pages: number
}
