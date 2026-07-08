export type ReviewProvider = 'kling' | 'comfy_video' | 'comfy_image'

export type ReviewStatus =
  | 'pending_review'
  | 'approved'
  | 'dispatched'
  | 'completed'
  | 'failed'
  | 'discarded'

export interface ReviewRequestItem {
  id: string
  batch_id: string
  source_image_path: string
  original_prompt: string
  prompt: string
  provider: ReviewProvider
  workflow_name: string | null
  settings: Record<string, unknown>
  status: ReviewStatus
  execution_id: string | null
  result_path: string | null
  error: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ReviewListResponse {
  items: ReviewRequestItem[]
  total: number
  page: number
  pages: number
}

export interface ReviewItemCreate {
  source_image_path: string
  prompt: string
  provider: ReviewProvider
  workflow_name?: string | null
  settings?: Record<string, unknown>
}

export interface ReviewCreateResponse {
  batch_id: string
  request_ids: string[]
}

export interface ReviewDispatchResponse {
  dispatched: string[]
  skipped: string[]
}
