import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { ImageMetadataDetails } from '@/components/gallery/ImageMetadataDetails'
import type { ImageMetadata } from '@/types'

afterEach(cleanup)

const metadata: ImageMetadata = {
  persona: 'Emi',
  seed: 401848280151638,
  prompt: 'A medium close-up shot at eye level.',
  workflow: 'Z-image-control-net.json',
  workflow_note: '',
}

const renderDetails = (overrides: Partial<ImageMetadata> = {}) =>
  render(<ImageMetadataDetails metadata={{ ...metadata, ...overrides }} />)

describe('ImageMetadataDetails', () => {
  it('names the workflow that produced the image', () => {
    renderDetails()

    expect(screen.getByText('Workflow')).toBeTruthy()
    expect(screen.getByText('Z-image-control-net.json')).toBeTruthy()
  })

  it('omits the workflow row when the image predates recording it', () => {
    renderDetails({ workflow: null })

    expect(screen.queryByText('Workflow')).toBeNull()
    // The rest of the metadata still renders.
    expect(screen.getByText('Emi')).toBeTruthy()
  })

  it('shows the note read-only — it is written in Configure › Workflows', () => {
    renderDetails({ workflow_note: 'Best for close-ups.' })

    fireEvent.click(screen.getByLabelText('Workflow note'))

    expect(screen.getByText('Best for close-ups.')).toBeTruthy()
    // No textarea, no Save: this panel never writes the note.
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByText('Save')).toBeNull()
  })

  it('points at where to write a note when there is none', () => {
    renderDetails()

    fireEvent.click(screen.getByLabelText('Workflow note'))

    expect(screen.getByText(/Configure › Workflows/)).toBeTruthy()
  })
})
