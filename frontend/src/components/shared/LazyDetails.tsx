import React, { useState } from 'react'

interface Props {
  summary: React.ReactNode
  /** Open on first mount. Not controlled afterwards — the user owns the toggle. */
  defaultOpen?: boolean
  className?: string
  summaryClassName?: string
  children: React.ReactNode
}

// A `<details>` that doesn't pay for what it hides.
//
// `<details>` collapses its children *visually*, but React still mounts every
// one of them: a Prompt Review page with four collapsed status sections was
// building ~17k DOM nodes and 2.7k inputs for content nobody could see, which
// cost ~3s on the stage switch. Gating the children on "has ever been open"
// keeps the native disclosure semantics (sticky summary, `group-open:` styling,
// keyboard, find-in-page on what's visible) and defers the rest.
//
// Children stay mounted after the first open, so collapsing a section never
// discards an in-progress edit or a scroll position.
export const LazyDetails: React.FC<Props> = ({
  summary,
  defaultOpen = false,
  className,
  summaryClassName,
  children,
}) => {
  const [everOpen, setEverOpen] = useState(defaultOpen)

  return (
    <details
      open={defaultOpen}
      className={className}
      onToggle={e => {
        if (e.currentTarget.open) setEverOpen(true)
      }}
    >
      <summary className={summaryClassName}>{summary}</summary>
      {everOpen && children}
    </details>
  )
}
