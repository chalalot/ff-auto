import React from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { FlowRail } from '@/components/flow/FlowRail'
import { CreatePanel } from '@/components/flow/CreatePanel'
import { GeneratingPanel } from '@/components/flow/GeneratingPanel'
import { ImageReviewPanel } from '@/components/flow/ImageReviewPanel'
import { ReviewQueueSection } from '@/components/review/ReviewQueueSection'
import { useFlowCounts, type FlowStage } from '@/hooks/useFlowCounts'

const STAGES: FlowStage[] = ['create', 'prompts', 'generating', 'images']

const isStage = (value: string | null): value is FlowStage =>
  value !== null && (STAGES as string[]).includes(value)

// The conveyor: pick images → approve prompts → watch them generate → judge the
// results. One image's trip, start to finish. The stage lives in the URL so a
// toast's "Open →" link, a deep link and the browser's back button are all the
// same mechanism.
//
// Dataset building and LoRA training used to sit here as a fifth stage, which
// mis-described them: they are not a step every image takes, they are a separate
// job that consumes the approved ones. They live at /lora.
export const FlowPage: React.FC = () => {
  const [params, setParams] = useSearchParams()
  const raw = params.get('stage')
  const counts = useFlowCounts()

  // Links and bookmarks from when Deliver was a stage.
  if (raw === 'deliver') return <Navigate to="/lora" replace />

  const stage: FlowStage = isStage(raw) ? raw : 'create'

  const go = (next: FlowStage) => {
    const updated = new URLSearchParams(params)
    updated.set('stage', next)
    setParams(updated, { replace: false })
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <FlowRail counts={counts} active={stage} onSelect={go} />

      {/* Only the active panel mounts — four panels' worth of polling at once
          would be four times the traffic for one visible list. This element
          owns the scroll, so sections can stick to its top. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {stage === 'create' && <CreatePanel />}
        {stage === 'prompts' && (
          <div className="px-4 py-3">
            <ReviewQueueSection />
          </div>
        )}
        {stage === 'generating' && <GeneratingPanel />}
        {stage === 'images' && <ImageReviewPanel />}
      </div>
    </div>
  )
}
