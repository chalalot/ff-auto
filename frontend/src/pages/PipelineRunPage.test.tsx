import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { pipelineApi } from '@/api/pipeline'
import { PipelineRunPage } from '@/pages/PipelineRunPage'
import type { PipelineRunTrace } from '@/types/pipeline'

vi.mock('@/api/pipeline', () => ({
  pipelineApi: {
    getRun: vi.fn(),
  },
}))

const trace: PipelineRunTrace = {
  id: 'run-1',
  pipeline_name: 'image_to_prompt',
  status: 'running',
  input_payload: { image_path: 'ref.png' },
  final_output: null,
  error: null,
  started_at: '2026-07-10T00:00:00Z',
  finished_at: null,
  created_at: '2026-07-10T00:00:00Z',
  updated_at: '2026-07-10T00:01:00Z',
  steps: [
    {
      id: 'step-1', run_id: 'run-1', step_key: 'vision_observation', sequence: 1,
      status: 'succeeded', input_payload: { image_path: 'ref.png' },
      system_prompt: null, rendered_context: { vision_prompt: 'observe' },
      output_payload: { observation: 'subject' }, usage: null, partial_output: null,
      error: null, model_name: 'gpt-4o', started_at: '2026-07-10T00:00:00Z',
      finished_at: '2026-07-10T00:00:10Z', created_at: '2026-07-10T00:00:00Z',
      updated_at: '2026-07-10T00:00:10Z',
    },
    {
      id: 'step-2', run_id: 'run-1', step_key: 'analyst', sequence: 2,
      status: 'running', input_payload: { observation: 'subject' },
      system_prompt: 'You are an analyst', rendered_context: [{ role: 'user', content: 'x' }],
      output_payload: null, usage: null, partial_output: null, error: null,
      model_name: 'gpt-4o', started_at: '2026-07-10T00:00:10Z', finished_at: null,
      created_at: '2026-07-10T00:00:10Z', updated_at: '2026-07-10T00:00:10Z',
    },
  ],
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/pipeline-runs/run-1']}>
        <Routes>
          <Route path="/pipeline-runs/:runId" element={<PipelineRunPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PipelineRunPage', () => {
  beforeEach(() => {
    vi.mocked(pipelineApi.getRun).mockResolvedValue(trace)
  })

  it('renders the ordered trace and selected step payloads', async () => {
    renderPage()

    expect(await screen.findByText('Image To Prompt')).toBeInTheDocument()
    expect(screen.getByText('Vision observation')).toBeInTheDocument()
    expect(screen.getAllByText('Analyst').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('You are an analyst')).toBeInTheDocument()
    expect(screen.getByText(/role.*user/)).toBeInTheDocument()
  })

  it('shows a failed step error', async () => {
    vi.mocked(pipelineApi.getRun).mockResolvedValue({
      ...trace,
      status: 'failed',
      steps: [{ ...trace.steps[1], status: 'failed', error: { type: 'ValueError', message: 'model failed' } }],
    })
    renderPage()

    expect(await screen.findByText(/model failed/)).toBeInTheDocument()
  })
})
