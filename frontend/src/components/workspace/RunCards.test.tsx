import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GlobalTaskCard } from '@/components/workspace/RunCards'
import type { ActiveTask } from '@/types'

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    getRefImageThumbnailUrl: vi.fn((filename: string) => `/thumbs/${filename}`),
    getTaskStatus: vi.fn(),
    dismissActiveTask: vi.fn(() => Promise.resolve({ dismissed: true })),
  },
}))

vi.mock('@/api/pipeline', () => ({ pipelineApi: { markFailed: vi.fn() } }))

// The card polls its own task on top of the 5s global refresh; with no live
// data it falls back to the row the registry handed it, which is what we assert.
vi.mock('@/hooks/useTaskProgress', () => ({
  useTaskProgress: () => ({ data: undefined }),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const task = (over: Partial<ActiveTask> = {}): ActiveTask => ({
  task_id: 'task-1',
  state: 'QUEUEING',
  status_message: '🎨 Queueing workflow on ComfyUI...',
  progress: 60,
  persona: '',
  task_type: 'image_process',
  ...over,
})

const renderCard = (t: ActiveTask) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <GlobalTaskCard task={t} />
      </MemoryRouter>
    </QueryClientProvider>,
  )

describe('GlobalTaskCard', () => {
  it('reads a failed task as an error, not as progress', () => {
    // The backend keeps a crashed task listed for 15 minutes with the exception
    // text as its status — the whole point is that the user can see it.
    renderCard(task({
      state: 'FAILURE',
      status_message: 'TypeError: expected str, bytes or os.PathLike object, not NoneType',
      progress: 0,
    }))

    const message = screen.getByText(/expected str, bytes/)
    expect(message.className).toContain('text-destructive')
    expect(screen.getByText('FAILURE')).toBeInTheDocument()
  })

  it('dismisses a failed task so the list can be cleaned', async () => {
    const { workspaceApi } = await import('@/api/workspace')
    renderCard(task({ state: 'FAILURE', status_message: 'google vision call failed: 503' }))

    fireEvent.click(screen.getByLabelText('Dismiss'))

    await waitFor(() => expect(workspaceApi.dismissActiveTask).toHaveBeenCalledWith('task-1'))
  })

  it('offers no dismiss while the task is still working', () => {
    // Clearing live work would hide it from every client, not just this one.
    renderCard(task())

    expect(screen.queryByLabelText('Dismiss')).toBeNull()
  })

  it('shows a running task without error styling', () => {
    renderCard(task())

    const message = screen.getByText(/Queueing workflow/)
    expect(message.className).not.toContain('text-destructive')
  })

  it('renders a text-to-image task, which has no source image', () => {
    // image_path is null for T2I: no thumbnail to show, and nothing may throw.
    renderCard(task({ image_path: undefined, status_message: '⏳ Preparing ZIB-ZIT.json...' }))

    expect(screen.getByText(/Preparing ZIB-ZIT/)).toBeInTheDocument()
    expect(screen.queryByRole('img')).toBeNull()
  })
})
