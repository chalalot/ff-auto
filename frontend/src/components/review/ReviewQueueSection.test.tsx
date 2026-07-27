import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { workspaceApi } from '@/api/workspace'
import { RequestRow } from '@/components/review/ReviewQueueSection'
import type { ReviewRequestItem } from '@/types/review'

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    getWorkflowParameters: vi.fn(),
    getRefImageThumbnailUrl: vi.fn((filename: string) => `/thumbs/${filename}`),
  },
}))

vi.mock('@/api/review', () => ({
  reviewApi: {
    getThumbnailUrl: vi.fn(() => '/thumb.png'),
    updateRequest: vi.fn(),
    discardRequest: vi.fn(),
    redispatch: vi.fn(),
  },
}))

afterEach(cleanup)

const item: ReviewRequestItem = {
  id: 'request-1',
  batch_id: 'batch-1',
  source_image_path: '/app/processed/ref.jpg',
  original_prompt: '#Subject\nx\n#Environment\ny',
  prompt: '#Subject\nx\n#Environment\ny',
  provider: 'comfy_image',
  workflow_name: 'Z-image-control-net.json',
  settings: {
    persona: 'Emi',
    workflow_type: 'image_generation',
    vision_model: 'grok-4.3',
    width: 1024,
    height: 1600,
    workflow_overrides: {
      '11': { seed: 140274352381802, steps: 8 },
      '16': { lora_name: 'emi.safetensors', strength_model: 1.15 },
    },
  },
  status: 'completed',
  execution_id: 'execution-1',
  result_path: '/app/results/result.png',
  error: null,
  created_at: '2026-07-10T00:00:00Z',
  updated_at: '2026-07-10T00:00:01Z',
}

function renderRow(overrides: Partial<ReviewRequestItem> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <RequestRow item={{ ...item, ...overrides }} checked={false} onToggle={() => undefined} />
    </QueryClientProvider>,
  )
}

describe('ReviewQueueSection parameter ownership', () => {
  it('renders workflow-owned values only in Workflow Parameters', async () => {
    vi.mocked(workspaceApi.getWorkflowParameters).mockResolvedValue({
      workflow: 'Z-image-control-net.json',
      nodes: [],
    })

    renderRow()

    // Seeds, LoRA, dimensions, and workflow type are workflow-owned now —
    // edited only through the parsed Workflow Parameters, never app-level UI.
    expect(screen.queryByText('Seed Strategy')).not.toBeInTheDocument()
    expect(screen.queryByText('Base Seed')).not.toBeInTheDocument()
    expect(screen.queryByText('Workflow Type')).not.toBeInTheDocument()
    expect(screen.queryByText('LoRA')).not.toBeInTheDocument()
    expect(screen.queryByText('Strength')).not.toBeInTheDocument()
    expect(screen.queryByText('Width')).not.toBeInTheDocument()
    expect(screen.queryByText('Height')).not.toBeInTheDocument()
    expect(screen.getByText('Workflow Parameters (Z-image-control-net)')).toBeInTheDocument()
  })

  it('keeps the AI pipeline settings editable', () => {
    renderRow()

    expect(screen.getByText('Persona')).toBeInTheDocument()
    expect(screen.getByText('Vision Model')).toBeInTheDocument()
  })

  it('renders LoadImage image input as a dropdown, not a text field', async () => {
    vi.mocked(workspaceApi.getWorkflowParameters).mockResolvedValue({
      workflow: 'Z-image-control-net.json',
      nodes: [
        {
          node_id: '78',
          class_type: 'LoadImage',
          title: 'Load Image',
          inputs: [
            { key: 'image', value: 'abc123.png', type: 'string', locked: false, locked_reason: null },
          ],
        },
      ],
    })

    renderRow()

    // Workflow value shown in the select trigger; no free-text input for it.
    expect(await screen.findByText('abc123.png')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('abc123.png')).not.toBeInTheDocument()
  })
})

describe('stale override warning', () => {
  it('stays quiet when every saved override still resolves', () => {
    renderRow({ stale_overrides: [] })

    expect(screen.queryByTestId('stale-overrides-badge')).not.toBeInTheDocument()
  })

  it('flags overrides the workflow no longer has and names them', () => {
    renderRow({ stale_overrides: ['11.seed', '16.lora_name'] })

    expect(screen.getByTestId('stale-overrides-badge')).toHaveTextContent('2 stale overrides')
    expect(screen.getByText('11.seed, 16.lora_name')).toBeInTheDocument()
  })

  it('singularises a lone stale override', () => {
    renderRow({ stale_overrides: ['11.seed'] })

    expect(screen.getByTestId('stale-overrides-badge')).toHaveTextContent('1 stale override')
  })
})
