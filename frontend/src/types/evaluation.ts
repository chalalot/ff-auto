export type EvaluationMediaType = 'image' | 'video'
export type EvaluationStatus = 'pending' | 'completed' | 'failed'

export interface EvaluationRequest {
  media_type: EvaluationMediaType
  media_path: string
  prompt?: string | null
}

export interface EvaluationScore {
  dimension: string
  score: number
  rationale: string
}

export interface EvaluationResult {
  id: number
  status: EvaluationStatus
  media_type: EvaluationMediaType
  media_path: string
  prompt?: string | null
  model: string
  rubric_version: string
  scores: EvaluationScore[]
  overall_score?: number | null
  summary?: string | null
  error_message?: string | null
  created_at: string
  completed_at?: string | null
}

export interface EvaluationListResponse {
  items: EvaluationResult[]
}
