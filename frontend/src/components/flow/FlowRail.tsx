import React from 'react'
import { cn } from '@/lib/utils'
import { ChevronRight, FileText, ImagePlus, Loader2, Sparkles, Star } from 'lucide-react'
import type { FlowCounts, FlowStage, StageTone } from '@/hooks/useFlowCounts'

const STAGES: Array<{
  stage: FlowStage
  label: string
  icon: React.FC<React.SVGProps<SVGSVGElement>>
}> = [
  { stage: 'create', label: 'Create', icon: ImagePlus },
  { stage: 'prompts', label: 'Prompt Review', icon: FileText },
  { stage: 'generating', label: 'Generating', icon: Sparkles },
  { stage: 'images', label: 'Image Review', icon: Star },
]

// The count pill carries the state, so the tone is on the pill rather than the
// whole chip — the rail stays readable when three stages are non-idle at once.
const PILL_TONE: Record<StageTone, string> = {
  attn: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30',
  busy: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30',
  done: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
  idle: 'bg-muted text-muted-foreground border-transparent',
}

export const FlowRail: React.FC<{
  counts: FlowCounts
  active: FlowStage
  onSelect: (stage: FlowStage) => void
}> = ({ counts, active, onSelect }) => (
  <nav
    aria-label="Flow stages"
    className="flex items-stretch gap-1 overflow-x-auto border-b bg-card px-3 py-2"
  >
    {STAGES.map(({ stage, label, icon: Icon }, i) => {
      const { count, tone, detail } = counts[stage]
      const isActive = stage === active
      return (
        <React.Fragment key={stage}>
          {i > 0 && (
            <ChevronRight className="w-4 h-4 shrink-0 self-center text-muted-foreground/40" />
          )}
          <button
            type="button"
            onClick={() => onSelect(stage)}
            aria-current={isActive ? 'step' : undefined}
            className={cn(
              'flex shrink-0 items-center gap-2.5 rounded-md border px-3 py-1.5 text-left transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              isActive
                ? 'border-primary/40 bg-accent'
                : 'border-transparent hover:bg-accent/60',
            )}
          >
            {stage === 'generating' && tone === 'busy' ? (
              <Loader2 className="w-4 h-4 shrink-0 animate-spin text-amber-600 dark:text-amber-400" />
            ) : (
              <Icon
                className={cn(
                  'w-4 h-4 shrink-0',
                  isActive ? 'text-foreground' : 'text-muted-foreground',
                )}
              />
            )}
            <span className="min-w-0">
              <span className="flex items-center gap-1.5">
                <span className={cn('text-sm font-medium', !isActive && 'text-muted-foreground')}>
                  {label}
                </span>
                <span
                  className={cn(
                    'rounded-full border px-1.5 text-[11px] font-semibold tabular-nums',
                    PILL_TONE[tone],
                  )}
                >
                  {count}
                </span>
              </span>
              <span className="block text-[11px] leading-tight text-muted-foreground/70">
                {detail}
              </span>
            </span>
          </button>
        </React.Fragment>
      )
    })}
  </nav>
)
