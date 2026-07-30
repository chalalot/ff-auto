import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Clock, Loader2 } from 'lucide-react'
import { GalleryBrowser } from '@/components/gallery/GalleryBrowser'
import { ExecutionCard, PipelineRunHistoryCard } from '@/components/workspace/RunCards'
import { ArchivePage } from '@/pages/ArchivePage'
import { useGalleryStats } from '@/hooks/useGalleryImages'
import { useProjectId } from '@/hooks/useProjectId'
import { workspaceApi } from '@/api/workspace'
import { pipelineApi } from '@/api/pipeline'
import type { PipelineRunSummary } from '@/types/pipeline'

// Everything already judged: approved and disapproved images, the read-only
// archive, and the record of what produced them. Pending images are not here —
// they are work, so they live in Flow › Image Review.
export const LibraryPage: React.FC = () => {
  const projectId = useProjectId() ?? undefined
  const [tab, setTab] = useState('approved')
  const { data: stats } = useGalleryStats(projectId)
  const totals = stats?.totals || { pending: 0, approved: 0, disapproved: 0 }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-4 border-b p-4">
        <h1 className="text-xl font-bold">Library</h1>
        <div className="flex gap-3 text-sm">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-success" />
            {totals.approved} approved
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-destructive" />
            {totals.disapproved} disapproved
          </span>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="flex flex-1 flex-col overflow-hidden">
        <TabsList className="mx-4 mt-4 w-fit">
          <TabsTrigger value="approved">
            Approved <Badge variant="outline" className="ml-2 text-xs">{totals.approved}</Badge>
          </TabsTrigger>
          <TabsTrigger value="disapproved">
            Disapproved <Badge variant="outline" className="ml-2 text-xs">{totals.disapproved}</Badge>
          </TabsTrigger>
          <TabsTrigger value="archive">Archive</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        {/* Each browser keeps its own page/selection, so switching tabs can't
            carry a selection into a status whose actions differ.
            The tab owns the scroll and lets the grid grow — pinning a definite
            height here instead makes the grid share it between rows and clips
            every card's filename and buttons. */}
        <TabsContent value="approved" className="flex-1 overflow-auto">
          <GalleryBrowser status="approved" />
        </TabsContent>
        <TabsContent value="disapproved" className="flex-1 overflow-auto">
          <GalleryBrowser status="disapproved" />
        </TabsContent>
        <TabsContent value="archive" className="flex-1 overflow-hidden">
          <ArchivePage />
        </TabsContent>
        <TabsContent value="history" className="flex-1 overflow-auto px-4 pb-4">
          <HistoryTab projectId={projectId} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

const HistoryTab: React.FC<{ projectId?: string }> = ({ projectId }) => {
  const { data: executions = [] } = useQuery({
    queryKey: ['workspace', 'executions', projectId ?? 'all'],
    queryFn: () => workspaceApi.getExecutions({ limit: 20, project_id: projectId }),
  })
  const { data: pipelineRuns = [], isLoading: pipelineRunsLoading } = useQuery<PipelineRunSummary[]>({
    queryKey: ['pipeline-runs', projectId ?? 'all'],
    queryFn: () => pipelineApi.listRuns({ limit: 20, project_id: projectId }),
    // Fast only while a run is in flight; slow refresh keeps the list current
    // when runs are started elsewhere (other tabs/users).
    refetchInterval: query =>
      (query.state.data ?? []).some(r => r.status === 'queued' || r.status === 'running')
        ? 5000
        : 30000,
  })

  // A run that stalled weeks ago sits outside the newest-20 window above, so it
  // would never appear here — and it is exactly the run that needs closing out.
  const { data: inFlight = [] } = useQuery<PipelineRunSummary[]>({
    queryKey: ['pipeline-runs', 'in-flight', projectId ?? 'all'],
    queryFn: () => pipelineApi.listRuns({ limit: 100, project_id: projectId, in_flight: true }),
    refetchInterval: 30000,
  })
  const recentIds = new Set(pipelineRuns.map(r => r.id))
  const stalled = inFlight.filter(r => !recentIds.has(r.id))

  return (
    <div className="space-y-6 pt-4">
      {stalled.length > 0 && (
        <section className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
          <div>
            <h2 className="text-sm font-semibold">Never finished</h2>
            <p className="text-xs text-muted-foreground">
              {stalled.length === 1 ? 'This run is' : 'These runs are'} still marked in flight but
              no worker is working on {stalled.length === 1 ? 'it' : 'them'}. Marking
              {stalled.length === 1 ? ' it' : ' them'} failed closes {stalled.length === 1 ? 'it' : 'them'} out.
            </p>
          </div>
          {stalled.map(run => <PipelineRunHistoryCard key={run.id} run={run} />)}
        </section>
      )}

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Pipeline Runs</h2>
            <p className="text-xs text-muted-foreground">Reopen a run to inspect every agent prompt, context, and output.</p>
          </div>
          {pipelineRunsLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        </div>
        {pipelineRuns.length === 0 && !pipelineRunsLoading ? (
          <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">No pipeline runs yet.</div>
        ) : (
          pipelineRuns.map(run => <PipelineRunHistoryCard key={run.id} run={run} />)
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Legacy Executions</h2>
        {executions.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground">
            <Clock className="mx-auto mb-4 h-12 w-12 opacity-50" />
            <p>No executions yet</p>
          </div>
        ) : (
          executions.map(exec => <ExecutionCard key={exec.execution_id} exec={exec} />)
        )}
      </section>
    </div>
  )
}
