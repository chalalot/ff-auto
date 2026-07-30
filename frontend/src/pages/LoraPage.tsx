import React from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Loader2 } from 'lucide-react'
import { CaptionExportTab } from '@/components/workspace/CaptionExportTab'
import { DEFAULT_CONFIG } from '@/lib/configDefaults'
import { usePersonas, useVisionModels, useLastUsed } from '@/hooks/usePersonas'
import { useActiveTasks } from '@/hooks/useActiveTasks'
import { useFlowCounts } from '@/hooks/useFlowCounts'

// Build a captioned dataset and train a character LoRA on it.
//
// This is not a stage of the Flow conveyor — it doesn't happen to each image on
// its way through. It's a separate job that consumes a *set* of already-approved
// images, runs its own captioning pass, packages them, and hands the result to
// RunPod. Modelling it as a fifth stage implied every image ends up here, which
// isn't how it's used.
export const LoraPage: React.FC = () => {
  const { data: personas = [] } = usePersonas()
  const { data: visionModels = [] } = useVisionModels()
  const { data: activeTasks = [] } = useActiveTasks()
  const { data: lastUsed, isFetched } = useLastUsed()
  const { approved } = useFlowCounts()

  // CaptionExportTab seeds its persona/model pickers from defaultConfig once, on
  // mount — so wait for the real values instead of mounting it with blanks.
  if (!isFetched || personas.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b p-4">
        <h1 className="text-xl font-bold">LoRA</h1>
        <p className="text-sm text-muted-foreground">
          Caption a set of images into a dataset, then train a character LoRA on it.
        </p>
        {/* The dataset comes from approved images, so say how many there are and
            offer the way to make more. */}
        <Link
          to={approved > 0 ? '/library' : '/flow?stage=images'}
          className="ml-auto inline-flex shrink-0 items-center gap-1 text-xs font-medium text-blue-700 hover:underline"
        >
          {approved > 0
            ? `${approved} approved image${approved === 1 ? '' : 's'} available`
            : 'No approved images yet — judge some first'}
          <ArrowRight className="h-3 w-3" aria-hidden="true" />
        </Link>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <CaptionExportTab
          personas={personas}
          visionModels={visionModels}
          defaultConfig={{
            ...DEFAULT_CONFIG,
            persona: lastUsed?.persona || personas[0]?.name || '',
            vision_model: lastUsed?.vision_model || DEFAULT_CONFIG.vision_model,
          }}
          activeTasks={activeTasks}
        />
      </div>
    </div>
  )
}
