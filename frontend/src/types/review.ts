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
  project_id?: string | null
  created_by_member_id?: string | null
  created_at: string | null
  updated_at: string | null
  // "<node_id>.<input_key>" for saved overrides the current workflow JSON no
  // longer accepts; they are dropped silently at dispatch.
  stale_overrides?: string[]
}

export interface ReviewListResponse {
  items: ReviewRequestItem[]
  total: number
  page: number
  pages: number
  // Rows per status across the whole queue — project scope applies, the status
  // filter and pagination do not. Statuses with no rows are absent, so read it
  // through `??  0`. The Flow rail counts from this, never from `items`, which
  // is capped at per_page.
  status_counts?: Partial<Record<ReviewStatus, number>>
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
