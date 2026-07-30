import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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

// Call history is per-test — one test asserts the schema request has *not*
// happened yet, which an earlier test's call would otherwise satisfy.
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

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

// A row's parameters panel — and each node group inside it — is only mounted
// once its disclosure is opened, so a queue of hundreds of rows doesn't build a
// form nobody asked for. jsdom doesn't implement <details> activation, so open
// it the way the browser would: set `open`, then fire the toggle React listens
// for. Pass any element inside the summary.
function openDisclosure(inSummary: HTMLElement) {
  const details = inSummary.closest('details') as HTMLDetailsElement
  details.open = true
  // `toggle` doesn't bubble and isn't in fireEvent's map — dispatch it directly.
  fireEvent(details, new Event('toggle'))
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

    openDisclosure(screen.getByText('Workflow Parameters (Z-image-control-net)'))
    openDisclosure(await screen.findByText('LoadImage'))

    // Workflow value shown in the select trigger; no free-text input for it.
    expect(await screen.findByText('abc123.png')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('abc123.png')).not.toBeInTheDocument()
  })

  it('defers the parameters panel and its schema request until opened', async () => {
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

    // Rendering the panel for every row cost ~3s on the Prompt Review switch.
    expect(screen.queryByText('reset')).not.toBeInTheDocument()
    expect(workspaceApi.getWorkflowParameters).not.toHaveBeenCalled()

    openDisclosure(screen.getByText('Workflow Parameters (Z-image-control-net)'))

    expect(await screen.findByText('reset')).toBeInTheDocument()
    expect(workspaceApi.getWorkflowParameters).toHaveBeenCalledWith('Z-image-control-net.json')
    // The node group is a second disclosure — its fields wait too.
    expect(screen.queryByText('abc123.png')).not.toBeInTheDocument()
  })
})

describe('stale override warning', () => {
  it('stays quiet when every saved override still resolves', () => {
    renderRow({ stale_overrides: [] })

    expect(screen.queryByTestId('stale-overrides-badge')).not.toBeInTheDocument()
  })

  it('flags overrides the workflow no longer has and names them', async () => {
    renderRow({ stale_overrides: ['11.seed', '16.lora_name'] })

    // The badge is always visible — it is the row's warning. The names sit with
    // the fields they belong to, inside the deferred panel.
    expect(screen.getByTestId('stale-overrides-badge')).toHaveTextContent('2 stale overrides')

    openDisclosure(screen.getByText('Workflow Parameters (Z-image-control-net)'))

    expect(await screen.findByText('11.seed, 16.lora_name')).toBeInTheDocument()
  })

  it('singularises a lone stale override', () => {
    renderRow({ stale_overrides: ['11.seed'] })

    expect(screen.getByTestId('stale-overrides-badge')).toHaveTextContent('1 stale override')
  })
})
