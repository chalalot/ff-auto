import { useQuery } from '@tanstack/react-query'
import { workspaceApi } from '@/api/workspace'
import { useReviewRequests } from '@/hooks/useReviewRequests'
import { useGalleryStats } from '@/hooks/useGalleryImages'
import { useActiveTasks } from '@/hooks/useActiveTasks'
import { useProjectId } from '@/hooks/useProjectId'
import { IMAGE_PROVIDERS } from '@/lib/providers'

// The conveyor, and only the conveyor: one image's trip from reference to
// judged result. Building a training dataset and training a character LoRA is a
// separate job that consumes approved images — it lives at /lora, not here.
export type FlowStage = 'create' | 'prompts' | 'generating' | 'images'

// How a stage's count reads at a glance: red = a human is blocking the line,
// amber = a machine is working, green = ready to ship, idle = nothing to do.
export type StageTone = 'attn' | 'busy' | 'done' | 'idle'

export interface StageCount {
  count: number
  tone: StageTone
  /** Sub-caption under the chip label; '' when the stage is idle. */
  detail: string
}

export type FlowCounts = Record<FlowStage, StageCount> & {
  /** Everything waiting on a human — the Flow sidebar badge. */
  waiting: number
  /** Approved images available to build a dataset from — the LoRA badge. */
  approved: number
}

const TERMINAL = new Set(['SUCCESS', 'FAILURE', 'REVOKED'])

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

// Single source for every counter on the Flow surface. All four underlying
// queries are already mounted elsewhere in the app (or cheap and staleTime'd),
// so the rail rides their caches rather than adding polling of its own.
export const useFlowCounts = (): FlowCounts => {
  const projectId = useProjectId() ?? undefined
  // Image work only. Video rows live in the same queue but on their own surface,
  // so counting them here would report video jobs as prompts to approve.
  const { data: review } = useReviewRequests(IMAGE_PROVIDERS)
  const { data: galleryStats } = useGalleryStats(projectId)
  const { data: activeTasks = [] } = useActiveTasks()
  const { data: library = [] } = useQuery({
    queryKey: ['workspace', 'ref-images', projectId ?? 'all'],
    queryFn: () => workspaceApi.getRefImages({ project_id: projectId }),
  })

  // status_counts is the whole-queue tally. Fall back to counting the fetched
  // rows if it is absent — a backend older than the field would otherwise make
  // every stage read zero while rows sat in the queue.
  const items = review?.items ?? []
  const counts = review?.status_counts
    ?? items.reduce<Record<string, number>>((acc, i) => {
      acc[i.status] = (acc[i.status] ?? 0) + 1
      return acc
    }, {})
  const pending = counts.pending_review ?? 0
  const failed = counts.failed ?? 0
  const dispatched = counts.dispatched ?? 0
  const busyTasks = activeTasks.filter(t => !TERMINAL.has(t.state)).length
  const toReview = galleryStats?.totals.pending ?? 0
  const approved = galleryStats?.totals.approved ?? 0

  // A failure mid-generation is the machine stopping, so it turns the amber
  // chip red — but the rows themselves stay in Prompt Review › Failed, which is
  // where they can be retried.
  const generating = dispatched + busyTasks

  return {
    create: {
      count: library.length,
      tone: 'idle',
      detail: library.length ? plural(library.length, 'image') : 'no images yet',
    },
    prompts: {
      count: pending + failed,
      tone: pending + failed > 0 ? 'attn' : 'idle',
      detail: failed
        ? `${pending} pending · ${plural(failed, 'failure')}`
        : pending
          ? `${plural(pending, 'prompt')} to approve`
          : 'nothing to review',
    },
    generating: {
      count: generating,
      tone: failed > 0 ? 'attn' : generating > 0 ? 'busy' : 'idle',
      detail: generating
        ? plural(generating, 'job', 'jobs') + ' running'
        : failed
          ? plural(failed, 'failure')
          : 'idle',
    },
    images: {
      count: toReview,
      tone: toReview > 0 ? 'attn' : 'idle',
      detail: toReview ? plural(toReview, 'image') + ' to judge' : 'nothing to judge',
    },
    waiting: pending + failed + toReview,
    approved,
  }
}
