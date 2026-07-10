import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PipelineStepInspector } from '@/components/pipeline/PipelineStepInspector'
import type { PipelineStepTrace } from '@/types/pipeline'

const step: PipelineStepTrace = {
  id: 'step-1', run_id: 'run-1', step_key: 'analyst', sequence: 2,
  status: 'succeeded', input_payload: { observation: 'subject' },
  system_prompt: 'system', rendered_context: {
    workflow_context: [{ role: 'user', content: 'context' }],
    tool_calls: [{ tool: 'Skill Reader', input: { ref_path: 'SKILL.md' }, output: 'skill contents' }],
  },
  output_payload: { result: 'output' }, usage: { input_tokens: 4 }, partial_output: null,
  error: null, model_name: 'gpt-4o', started_at: null, finished_at: null,
  created_at: null, updated_at: null,
}

describe('PipelineStepInspector', () => {
  it('renders all read-only payload sections', () => {
    render(<PipelineStepInspector step={step} />)

    expect(screen.getByText('Input')).toBeInTheDocument()
    expect(screen.getByText('System Prompt')).toBeInTheDocument()
    expect(screen.getByText('Context')).toBeInTheDocument()
    expect(screen.getByText('Tool Calls')).toBeInTheDocument()
    expect(screen.getByText('Output')).toBeInTheDocument()
    expect(screen.getByText('Metadata')).toBeInTheDocument()
    expect(screen.getByText(/system/)).toBeInTheDocument()
    expect(screen.getAllByText(/output/).length).toBeGreaterThan(0)
  })
})
