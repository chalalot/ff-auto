import React, { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { Loader2, X, ChevronLeft, ChevronRight } from 'lucide-react'
import { analysisApi } from '@/api/analysis'
import { galleryApi } from '@/api/gallery'
import type {
  AnalysisRow,
  AnalysisStatusFilter,
  EvaluatedFilter,
} from '@/types/analysis'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const pct = (rate: number) => `${(rate * 100).toFixed(0)}%`
const STATUS_VARIANT: Record<string, string> = {
  approved: 'bg-green-500/15 text-green-700 dark:text-green-400',
  disapproved: 'bg-red-500/15 text-red-700 dark:text-red-400',
  pending: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </Card>
  )
}

function ScoreCell({ row }: { row: AnalysisRow }) {
  if (row.eval_status !== 'completed') {
    return <span className="text-xs text-muted-foreground">{row.eval_status.replace('_', ' ')}</span>
  }
  return (
    <div className="space-y-1.5 max-w-md">
      {row.scores.map(s => (
        <div key={s.dimension} className="text-xs">
          <span className="font-medium">{s.dimension.replace(/_/g, ' ')}: </span>
          <span className="tabular-nums">{s.score}/5</span>
          <span className="text-muted-foreground"> — {s.rationale}</span>
        </div>
      ))}
      <div className="text-sm font-semibold pt-1">
        Avg: {row.overall_score?.toFixed(2) ?? '—'}
      </div>
    </div>
  )
}

function Lightbox({ row, onClose }: { row: AnalysisRow; onClose: () => void }) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-card rounded-lg max-w-5xl w-full max-h-[90vh] overflow-auto p-4 grid grid-cols-1 md:grid-cols-2 gap-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="relative">
          <img
            src={galleryApi.getThumbnailUrl(row.filename, row.status)}
            alt={row.filename}
            className="w-full rounded-md object-contain"
          />
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs break-all">{row.filename}</span>
            <button onClick={onClose} className="p-1 hover:bg-accent rounded">
              <X className="w-4 h-4" />
            </button>
          </div>
          <Badge className={STATUS_VARIANT[row.status]}>{row.status}</Badge>
          <ScoreCell row={row} />
          {row.prompt && (
            <div className="text-xs">
              <div className="font-medium">Prompt</div>
              <p className="text-muted-foreground whitespace-pre-wrap">{row.prompt}</p>
            </div>
          )}
          {row.persona && (
            <div className="text-xs">
              <span className="font-medium">Persona: </span>
              <span className="text-muted-foreground">{row.persona}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export const AnalysisPage: React.FC = () => {
  const [status, setStatus] = useState<AnalysisStatusFilter>('all')
  const [evaluated, setEvaluated] = useState<EvaluatedFilter>('all')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<AnalysisRow | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analysis', status, evaluated, page],
    queryFn: () => analysisApi.list({ status, evaluated, page, per_page: 25 }),
    placeholderData: keepPreviousData,
  })

  const onFilter = (fn: () => void) => {
    fn()
    setPage(1)
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Analysis</h1>
        <p className="text-sm text-muted-foreground">Scoring and approval overview across all generated images.</p>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard label="Avg Score" value={data.summary.avg_overall_score?.toFixed(2) ?? '—'} sub={`${data.summary.total} images`} />
          <StatCard label="Approved" value={`${data.summary.approval.approved}`} sub={pct(data.summary.approval.approved_rate)} />
          <StatCard label="Disapproved" value={`${data.summary.approval.disapproved}`} sub={pct(data.summary.approval.disapproved_rate)} />
          <StatCard label="Pending" value={`${data.summary.approval.pending}`} sub={pct(data.summary.approval.pending_rate)} />
          <StatCard label="Evaluated" value={`${data.summary.evaluation.evaluated}`} sub={pct(data.summary.evaluation.evaluated_rate)} />
          <StatCard label="Not Evaluated" value={`${data.summary.evaluation.not_evaluated}`} sub={pct(data.summary.evaluation.not_evaluated_rate)} />
        </div>
      )}

      <div className="flex flex-wrap gap-3 items-center">
        <select
          className="border rounded-md px-2 py-1 text-sm bg-background"
          value={status}
          onChange={e => onFilter(() => setStatus(e.target.value as AnalysisStatusFilter))}
        >
          <option value="all">All statuses</option>
          <option value="approved">Approved</option>
          <option value="disapproved">Disapproved</option>
          <option value="pending">Pending</option>
        </select>
        <select
          className="border rounded-md px-2 py-1 text-sm bg-background"
          value={evaluated}
          onChange={e => onFilter(() => setEvaluated(e.target.value as EvaluatedFilter))}
        >
          <option value="all">All</option>
          <option value="yes">Evaluated</option>
          <option value="no">Not evaluated</option>
        </select>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading analysis…
        </div>
      )}
      {isError && (
        <div className="text-sm text-red-600 flex items-center gap-3">
          Failed to load analysis.
          <Button variant="outline" size="sm" onClick={() => refetch()}>Retry</Button>
        </div>
      )}

      {data && (
        <>
          <div className="overflow-x-auto border rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th className="p-3 font-medium">Image</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Rubric Scores</th>
                  <th className="p-3 font-medium">Prompt / Persona</th>
                  <th className="p-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">No images match these filters.</td></tr>
                )}
                {data.items.map(row => (
                  <tr key={row.path} className="border-t hover:bg-accent/30">
                    <td className="p-3">
                      <button onClick={() => setSelected(row)} className="block">
                        <img
                          src={galleryApi.getThumbnailUrl(row.filename, row.status)}
                          alt={row.filename}
                          className="w-20 h-20 object-cover rounded-md hover:ring-2 ring-primary"
                          loading="lazy"
                        />
                      </button>
                    </td>
                    <td className="p-3 align-top">
                      <Badge className={STATUS_VARIANT[row.status]}>{row.status}</Badge>
                    </td>
                    <td className="p-3 align-top"><ScoreCell row={row} /></td>
                    <td className="p-3 align-top max-w-xs">
                      <div className="text-xs text-muted-foreground line-clamp-3 whitespace-pre-wrap">{row.prompt || '—'}</div>
                      {row.persona && <div className="text-xs mt-1"><span className="font-medium">Persona:</span> {row.persona}</div>}
                    </td>
                    <td className="p-3 align-top whitespace-nowrap text-xs text-muted-foreground">{row.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{data.total} images · page {data.page} / {data.pages}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                <ChevronLeft className="w-4 h-4" /> Prev
              </Button>
              <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>
                Next <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </>
      )}

      {selected && <Lightbox row={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
