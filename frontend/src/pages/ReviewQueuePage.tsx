import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, RotateCcw, Send, Trash2 } from 'lucide-react'
import { reviewApi } from '@/api/review'
import { projectsApi } from '@/api/projects'
import type { ReviewRequestItem, ReviewStatus } from '@/types/review'

const STATUS_BADGE: Record<ReviewStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending_review: 'secondary',
  approved: 'default',
  dispatched: 'default',
  completed: 'outline',
  failed: 'destructive',
  discarded: 'outline',
}

const PROVIDER_LABEL: Record<string, string> = {
  kling: 'Kling API',
  comfy_video: 'ComfyUI video',
  comfy_image: 'ComfyUI image',
}

const SELECTABLE: ReviewStatus[] = ['pending_review', 'failed']

function settingsEntries(settings: Record<string, unknown>): string[] {
  // Node overrides are applied last at dispatch, so they are the effective
  // values — show them and hide any top-level key they shadow.
  const overrides = (settings.workflow_overrides ?? {}) as Record<string, Record<string, unknown>>
  const overriddenKeys = new Set(
    Object.values(overrides).flatMap(patch => Object.keys(patch ?? {})),
  )
  const top = Object.entries(settings)
    .filter(([k, v]) =>
      v != null && v !== '' && k !== 'workflow_overrides' && k !== 'negative_prompt' && !overriddenKeys.has(k))
    .map(([k, v]) => `${k}=${String(v)}`)
  const over = Object.entries(overrides).flatMap(([nodeId, patch]) =>
    Object.entries(patch ?? {}).map(([k, v]) => `${k}[${nodeId}]=${String(v)}`),
  )
  return [...top, ...over]
}

// Mirrors the backend's subject/environment split (backend/pipelines/image.py):
// both markers present → the prompt is edited as two sections.
const SUBJECT_RE = /#Subject\s*([\s\S]*?)(?=#Environment|$)/i
const ENVIRONMENT_RE = /#Environment\s*([\s\S]*?)(?=#Subject|$)/i

function parsePromptSections(prompt: string): { subject: string; environment: string } | null {
  const sub = SUBJECT_RE.exec(prompt)
  const env = ENVIRONMENT_RE.exec(prompt)
  if (sub && env) return { subject: sub[1].trim(), environment: env[1].trim() }
  return null
}

function joinPromptSections(subject: string, environment: string): string {
  return `#Subject\n${subject.trim()}\n\n#Environment\n${environment.trim()}`
}

const SectionLabel: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
    {children}
  </p>
)

const RequestRow: React.FC<{
  item: ReviewRequestItem
  checked: boolean
  onToggle: (id: string) => void
  projectName?: string
}> = ({ item, checked, onToggle, projectName }) => {
  const queryClient = useQueryClient()
  const sections = parsePromptSections(item.prompt)
  const [subject, setSubject] = useState(sections?.subject ?? '')
  const [environment, setEnvironment] = useState(sections?.environment ?? '')
  const [plain, setPlain] = useState(sections ? '' : item.prompt)
  const editable = item.status === 'pending_review'

  const patchMutation = useMutation({
    mutationFn: (prompt: string) => reviewApi.updateRequest(item.id, { prompt }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })
  const discardMutation = useMutation({
    mutationFn: () => reviewApi.discardRequest(item.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })

  // Save on blur, only when content actually changed (canonical vs canonical).
  const saveSections = () => {
    if (!editable || !sections) return
    const next = joinPromptSections(subject, environment)
    if (next !== joinPromptSections(sections.subject, sections.environment)) {
      patchMutation.mutate(next)
    }
  }
  const savePlain = () => {
    if (!editable || sections) return
    if (plain !== item.prompt) patchMutation.mutate(plain)
  }

  return (
    <div className="flex gap-3 rounded-md border p-3" data-testid="review-row">
      <div className="flex items-start pt-1">
        <Checkbox
          checked={checked}
          disabled={!SELECTABLE.includes(item.status)}
          onCheckedChange={() => onToggle(item.id)}
        />
      </div>
      <img
        src={reviewApi.getThumbnailUrl(item.id)}
        alt=""
        className="h-20 w-20 rounded object-cover bg-muted shrink-0"
        onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden' }}
      />
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant={STATUS_BADGE[item.status]} className="text-xs capitalize">
            {item.status.replace('_', ' ')}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {PROVIDER_LABEL[item.provider] ?? item.provider}
          </Badge>
          {projectName && (
            <Badge variant="outline" className="text-xs">{projectName}</Badge>
          )}
          <span className="text-xs text-muted-foreground truncate">
            {item.source_image_path.split('/').pop()}
          </span>
        </div>
        {sections ? (
          <div className="space-y-2">
            <div className="space-y-1">
              <SectionLabel>Subject</SectionLabel>
              <Textarea
                value={subject}
                onChange={e => setSubject(e.target.value)}
                onBlur={saveSections}
                disabled={!editable}
                rows={3}
                className="text-sm"
              />
            </div>
            <div className="space-y-1">
              <SectionLabel>Environment</SectionLabel>
              <Textarea
                value={environment}
                onChange={e => setEnvironment(e.target.value)}
                onBlur={saveSections}
                disabled={!editable}
                rows={3}
                className="text-sm"
              />
            </div>
          </div>
        ) : (
          <Textarea
            value={plain}
            onChange={e => setPlain(e.target.value)}
            onBlur={savePlain}
            disabled={!editable}
            rows={3}
            className="text-sm"
          />
        )}
        {item.prompt !== item.original_prompt && (
          <p className="text-xs text-muted-foreground">edited (original kept)</p>
        )}
        <div className="flex flex-wrap gap-1">
          {settingsEntries(item.settings).map(entry => (
            <span
              key={entry}
              className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground break-all"
            >
              {entry}
            </span>
          ))}
        </div>
        {item.error && <p className="text-xs text-destructive break-words">{item.error}</p>}
      </div>
      {SELECTABLE.includes(item.status) && (
        <Button
          variant="ghost"
          size="icon"
          className="shrink-0"
          title="Discard"
          onClick={() => discardMutation.mutate()}
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      )}
    </div>
  )
}

export const ReviewQueuePage: React.FC<{ projectId?: string }> = ({ projectId }) => {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | 'all'>('pending_review')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['review-requests', statusFilter, projectId ?? 'all'],
    queryFn: () =>
      reviewApi.listRequests({
        status: statusFilter === 'all' ? undefined : statusFilter,
        per_page: 200,
        project_id: projectId,
      }),
    refetchInterval: 5000,
  })

  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects', 'all'],
    queryFn: () => projectsApi.list(true),
    enabled: !projectId,
  })
  const projectNames = new Map(allProjects.map(p => [p.id, p.name]))

  const items = useMemo(() => data?.items ?? [], [data])
  const batches = useMemo(() => {
    const map = new Map<string, ReviewRequestItem[]>()
    for (const item of items) {
      const group = map.get(item.batch_id) ?? []
      group.push(item)
      map.set(item.batch_id, group)
    }
    return Array.from(map.entries())
  }, [items])

  const toggle = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const toggleBatch = (batchItems: ReviewRequestItem[]) => {
    const selectable = batchItems.filter(i => SELECTABLE.includes(i.status)).map(i => i.id)
    setSelected(prev => {
      const next = new Set(prev)
      const allIn = selectable.every(id => next.has(id))
      selectable.forEach(id => (allIn ? next.delete(id) : next.add(id)))
      return next
    })
  }

  const dispatchMutation = useMutation({
    mutationFn: (ids: string[]) => reviewApi.dispatch(ids),
    onSuccess: () => {
      setSelected(new Set())
      void queryClient.invalidateQueries({ queryKey: ['review-requests'] })
    },
  })

  const selectedIds = Array.from(selected)

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between">
        <h1 className="text-xl font-bold">Review Queue</h1>
        <Tabs value={statusFilter} onValueChange={v => { setStatusFilter(v as ReviewStatus | 'all'); setSelected(new Set()) }}>
          <TabsList>
            <TabsTrigger value="pending_review">Pending</TabsTrigger>
            <TabsTrigger value="dispatched">Dispatched</TabsTrigger>
            <TabsTrigger value="completed">Completed</TabsTrigger>
            <TabsTrigger value="failed">Failed</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-6">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-12">
            No requests{statusFilter !== 'all' ? ` with status "${statusFilter.replace('_', ' ')}"` : ''}.
          </p>
        ) : (
          batches.map(([batchId, batchItems]) => (
            <section key={batchId} className="space-y-2">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Batch {batchId.slice(0, 8)} ({batchItems.length})
                </h2>
                {batchItems.some(i => SELECTABLE.includes(i.status)) && (
                  <Button variant="outline" size="sm" onClick={() => toggleBatch(batchItems)}>
                    Select all in batch
                  </Button>
                )}
              </div>
              <div className="space-y-2">
                {batchItems.map(item => (
                  <RequestRow
                    key={item.id}
                    item={item}
                    checked={selected.has(item.id)}
                    onToggle={toggle}
                    projectName={!projectId && item.project_id ? projectNames.get(item.project_id) : undefined}
                  />
                ))}
              </div>
            </section>
          ))
        )}
      </div>

      {selectedIds.length > 0 && (
        <div className="sticky bottom-0 border-t bg-card p-3 flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{selectedIds.length} selected</p>
          <Button
            onClick={() => dispatchMutation.mutate(selectedIds)}
            disabled={dispatchMutation.isPending}
          >
            {dispatchMutation.isPending ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Dispatching...</>
            ) : statusFilter === 'failed' ? (
              <><RotateCcw className="w-4 h-4 mr-2" />Retry selected ({selectedIds.length})</>
            ) : (
              <><Send className="w-4 h-4 mr-2" />Generate selected ({selectedIds.length})</>
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
