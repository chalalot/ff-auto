import type { EvaluationScore } from '@/types/evaluation'

export type ApprovalStatus = 'pending' | 'approved' | 'disapproved'
export type EvalRowStatus = 'completed' | 'pending' | 'failed' | 'not_evaluated'
export type AnalysisStatusFilter = 'all' | ApprovalStatus
export type EvaluatedFilter = 'all' | 'yes' | 'no'

export interface AnalysisRow {
  filename: string
  path: string
  status: ApprovalStatus
  date: string
  created_at: number
  prompt?: string | null
  persona?: string | null
  eval_status: EvalRowStatus
  overall_score?: number | null
  scores: EvaluationScore[]
}

export interface ApprovalBreakdown {
  approved: number
  disapproved: number
  pending: number
  approved_rate: number
  disapproved_rate: number
  pending_rate: number
}

export interface EvaluationBreakdown {
  evaluated: number
  not_evaluated: number
  failed: number
  evaluated_rate: number
  not_evaluated_rate: number
}

export interface AnalysisSummary {
  total: number
  approval: ApprovalBreakdown
  evaluation: EvaluationBreakdown
  avg_overall_score?: number | null
}

export interface AnalysisResponse {
  summary: AnalysisSummary
  items: AnalysisRow[]
  total: number
  page: number
  pages: number
  per_page: number
}
