/**
 * The metadata block under a result image: persona, workflow, seed, prompt.
 *
 * Shared by the gallery and archive detail modals, which showed the same four
 * fields in two copies of the same JSX.
 *
 * The workflow row carries an info button showing the note about that file —
 * what it is good for, what it struggles with. Read-only here: the note belongs
 * to the workflow rather than to this image, so it is written in one place
 * (Configure › Workflows) instead of from every result that used the graph.
 */
import React, { useEffect, useRef, useState } from 'react'
import { Info, Loader2, X } from 'lucide-react'
import type { ImageMetadata } from '@/types'

const Field: React.FC<{ label: React.ReactNode; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <div>
    <div className="text-xs text-muted-foreground mb-0.5">{label}</div>
    {children}
  </div>
)

const WorkflowNote: React.FC<{ workflow: string; note: string }> = ({
  workflow,
  note,
}) => {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // A different image may carry a different workflow; never show its note.
  const [seededFrom, setSeededFrom] = useState(workflow)
  if (seededFrom !== workflow) {
    setSeededFrom(workflow)
    setOpen(false)
  }

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  return (
    <div className="relative inline-flex" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        title={note || 'No note for this workflow'}
        aria-label="Workflow note"
        className={
          note
            ? 'text-primary hover:text-primary/80'
            : 'text-muted-foreground hover:text-foreground'
        }
      >
        <Info className="w-3.5 h-3.5" />
      </button>

      {open && (
        <div className="absolute left-0 top-6 z-10 w-80 rounded-lg border bg-background p-3 shadow-xl">
          <div className="flex items-start justify-between gap-2 mb-2">
            <p className="text-xs font-medium">Note · {workflow}</p>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          {note ? (
            <p className="text-sm whitespace-pre-wrap break-words">{note}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              No note yet — write one in Configure › Workflows.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export const ImageMetadataDetails: React.FC<{
  metadata: ImageMetadata | null
  loading?: boolean
}> = ({ metadata, loading = false }) => {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading metadata...
      </div>
    )
  }
  if (!metadata) return null

  const isEmpty =
    !metadata.persona &&
    !metadata.workflow &&
    metadata.seed == null &&
    !metadata.prompt

  return (
    <>
      {metadata.persona && (
        <Field label="Persona">
          <p className="text-sm">{metadata.persona}</p>
        </Field>
      )}
      {metadata.workflow && (
        <Field label="Workflow">
          <div className="flex items-center gap-1.5">
            <p className="text-sm font-mono break-all">{metadata.workflow}</p>
            <WorkflowNote
              workflow={metadata.workflow}
              note={metadata.workflow_note ?? ''}
            />
          </div>
        </Field>
      )}
      {metadata.seed != null && (
        <Field label="Seed">
          <p className="text-sm font-mono">{metadata.seed}</p>
        </Field>
      )}
      {metadata.prompt && (
        <Field label="Prompt">
          <p className="text-sm whitespace-pre-wrap break-words">{metadata.prompt}</p>
        </Field>
      )}
      {isEmpty && <p className="text-sm text-muted-foreground">No metadata available</p>}
    </>
  )
}
