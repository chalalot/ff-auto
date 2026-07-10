export type PipelineRunStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type PipelineStepStatus = PipelineRunStatus

export interface PipelineStepTrace {
  id: string
  run_id: string
  step_key: string
  sequence: number
  status: PipelineStepStatus
  input_payload: unknown
  system_prompt: string | null
  rendered_context: unknown
  output_payload: unknown
  usage: Record<string, unknown> | null
  partial_output: unknown
  error: Record<string, unknown> | null
  model_name: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface PipelineRunTrace {
  id: string
  pipeline_name: string
  status: PipelineRunStatus
  input_payload: unknown
  final_output: unknown
  error: Record<string, unknown> | null
  started_at: string | null
  finished_at: string | null
  created_at: string | null
  updated_at: string | null
  project_id?: string | null
  created_by_member_id?: string | null
  steps: PipelineStepTrace[]
}
