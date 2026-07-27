import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { AlertTriangle, Loader2, RefreshCcw, RotateCcw, Send, Trash2 } from 'lucide-react'
import { reviewApi } from '@/api/review'
import { projectsApi } from '@/api/projects'
import { workspaceApi } from '@/api/workspace'
import { useProjectId } from '@/hooks/useProjectId'
import { usePersonas, useVisionModels, useLoraOptions } from '@/hooks/usePersonas'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { WorkflowParametersPanel } from '@/components/workspace/WorkflowParametersPanel'
import type { ReviewRequestItem, ReviewStatus } from '@/types/review'
import type { WorkflowParameters, PersonaSummary } from '@/types'
import type { SelectOption } from '@/api/config'

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

const SELECTABLE: ReviewStatus[] = ['pending_review', 'failed', 'completed']

// Inline sections rendered in this order; empty statuses are skipped.
const STATUS_SECTIONS: Array<{ status: ReviewStatus; label: string }> = [
  { status: 'pending_review', label: 'Pending Review' },
  { status: 'dispatched', label: 'Dispatched' },
  { status: 'completed', label: 'Completed' },
  { status: 'failed', label: 'Failed' },
  { status: 'approved', label: 'Approved' },
  { status: 'discarded', label: 'Discarded' },
]

// Only actionable states are offered in the filter; approved/discarded still
// show as sections under "All states".
const FILTER_STATUSES = STATUS_SECTIONS.filter(
  s => s.status !== 'approved' && s.status !== 'discarded',
)

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

export const RequestRow: React.FC<{
  item: ReviewRequestItem
  checked: boolean
  onToggle: (id: string) => void
  projectName?: string
  personas?: PersonaSummary[]
  visionModels?: SelectOption[]
  loraOptions?: string[]
  imageOptions?: string[]
}> = ({
  item,
  checked,
  onToggle,
  projectName,
  personas = [],
  visionModels = [],
  loraOptions = [],
  imageOptions = [],
}) => {
  const queryClient = useQueryClient()
  const sections = parsePromptSections(item.prompt)
  const [subject, setSubject] = useState(sections?.subject ?? '')
  const [environment, setEnvironment] = useState(sections?.environment ?? '')
  const [plain, setPlain] = useState(sections ? '' : item.prompt)
  const editable =
    item.status === 'pending_review' ||
    item.status === 'failed' ||
    item.status === 'completed'

  const settingsObj = (item.settings ?? {}) as Record<string, unknown>
  // Saved overrides the workflow JSON no longer has. The graph is re-read at
  // dispatch, so an edit to the workflow can orphan these in place.
  const staleOverrides = item.stale_overrides ?? []

  const patchMutation = useMutation({
    mutationFn: (prompt: string) => reviewApi.updateRequest(item.id, { prompt }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })
  const settingsMutation = useMutation({
    mutationFn: (patch: Record<string, unknown>) =>
      reviewApi.updateRequest(item.id, { settings: { ...item.settings, ...patch } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })
  const discardMutation = useMutation({
    mutationFn: () => reviewApi.discardRequest(item.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })
  const redispatchMutation = useMutation({
    mutationFn: () => reviewApi.redispatch(item.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })
  const canRedispatch = item.status === 'completed' || item.status === 'failed'

  const workflowName = item.workflow_name || 'workflow.json'
  const {
    data: workflowParams = null,
    isLoading: paramsLoading,
    error: paramsError,
  } = useQuery<WorkflowParameters>({
    queryKey: ['workflow-params', workflowName],
    queryFn: () => workspaceApi.getWorkflowParameters(workflowName),
    enabled: editable && Boolean(workflowName),
  })

  const currentOverrides =
    (settingsObj.workflow_overrides ?? {}) as Record<string, Record<string, unknown>>

  const handleOverrideChange = (nodeId: string, key: string, value: unknown) => {
    const nextOverrides = {
      ...currentOverrides,
      [nodeId]: {
        ...(currentOverrides[nodeId] ?? {}),
        [key]: value,
      },
    }
    settingsMutation.mutate({ workflow_overrides: nextOverrides })
  }

  const saveSettingSelect = (key: string, value: unknown) => {
    if (!editable) return
    if (String(value ?? '') !== String(settingsObj[key] ?? '')) {
      settingsMutation.mutate({ [key]: value })
    }
  }

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
        onError={e => {
          ;(e.target as HTMLImageElement).style.visibility = 'hidden'
        }}
      />
      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant={STATUS_BADGE[item.status]} className="text-xs capitalize">
            {item.status.replace('_', ' ')}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {PROVIDER_LABEL[item.provider] ?? item.provider}
          </Badge>
          {projectName && (
            <Badge variant="outline" className="text-xs">
              {projectName}
            </Badge>
          )}
          {staleOverrides.length > 0 && (
            <Badge
              variant="destructive"
              className="text-xs gap-1"
              data-testid="stale-overrides-badge"
              title={`These saved values are not in ${workflowName} anymore and will fall back to the workflow's defaults: ${staleOverrides.join(', ')}`}
            >
              <AlertTriangle className="h-3 w-3" />
              {staleOverrides.length} stale override{staleOverrides.length > 1 ? 's' : ''}
            </Badge>
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

        {editable ? (
          <div className="space-y-2.5 pt-1">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {/* Persona */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Persona
                </label>
                <Select
                  value={String(settingsObj.persona || 'Jennie')}
                  onValueChange={v => saveSettingSelect('persona', v)}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {personas.length > 0 ? (
                      personas.map(p => (
                        <SelectItem key={p.name} value={p.name}>
                          {p.name}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value={String(settingsObj.persona || 'Jennie')}>
                        {String(settingsObj.persona || 'Jennie')}
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>

              {/* Vision Model */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Vision Model
                </label>
                <Select
                  value={String(settingsObj.vision_model || 'gpt-4o')}
                  onValueChange={v => saveSettingSelect('vision_model', v)}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {visionModels.length > 0 ? (
                      visionModels.map(vm => (
                        <SelectItem key={vm.value} value={vm.value}>
                          {vm.label}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value={String(settingsObj.vision_model || 'gpt-4o')}>
                        {String(settingsObj.vision_model || 'gpt-4o')}
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>

            </div>

            {item.workflow_name && (
              <details className="rounded border border-border/60 px-2.5 py-1.5 bg-muted/20">
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
                  Workflow Parameters ({item.workflow_name.replace(/\.json$/i, '')})
                </summary>
                <div className="mt-2.5 pt-2 border-t border-border/40">
                  {staleOverrides.length > 0 && (
                    <p className="mb-2 text-xs text-destructive">
                      No longer in this workflow — these fall back to the graph's defaults at
                      dispatch. Re-set them below, or Reset to clear.{' '}
                      <span className="font-mono break-all">{staleOverrides.join(', ')}</span>
                    </p>
                  )}
                  <WorkflowParametersPanel
                    params={workflowParams}
                    loading={paramsLoading}
                    error={paramsError ? 'Failed to load parameters' : null}
                    loraOptions={loraOptions}
                    imageOptions={imageOptions}
                    imageThumbnailUrl={workspaceApi.getRefImageThumbnailUrl}
                    values={currentOverrides}
                    onChange={handleOverrideChange}
                    onReset={() => settingsMutation.mutate({ workflow_overrides: {} })}
                  />
                </div>
              </details>
            )}
          </div>
        ) : (
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
        )}
        {item.error && <p className="text-xs text-destructive break-words">{item.error}</p>}
      </div>
      {SELECTABLE.includes(item.status) && (
        <div className="flex flex-col gap-1 shrink-0">
          {canRedispatch && (
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0"
              title="Regenerate to pending review"
              disabled={redispatchMutation.isPending}
              onClick={() => redispatchMutation.mutate()}
            >
              {redispatchMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCcw className="w-4 h-4" />
              )}
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0"
            title="Discard"
            onClick={() => discardMutation.mutate()}
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

function groupByBatch(items: ReviewRequestItem[]): Array<[string, ReviewRequestItem[]]> {
  const map = new Map<string, ReviewRequestItem[]>()
  for (const item of items) {
    const group = map.get(item.batch_id) ?? []
    group.push(item)
    map.set(item.batch_id, group)
  }
  return Array.from(map.entries())
}

export const ReviewQueueSection: React.FC = () => {
  const projectId = useProjectId() ?? undefined
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | 'all'>('all')
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

  const { data: personas = [] } = usePersonas()
  const { data: visionModels = [] } = useVisionModels()
  const { data: loraOptions = [] } = useLoraOptions()
  const { data: refImages = [] } = useQuery({
    queryKey: ['workspace', 'ref-images', projectId ?? 'all'],
    queryFn: () => workspaceApi.getRefImages({ project_id: projectId }),
  })

  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects', 'all'],
    queryFn: () => projectsApi.list(true),
    enabled: !projectId,
  })
  const projectNames = new Map(allProjects.map(p => [p.id, p.name]))

  const items = useMemo(() => data?.items ?? [], [data])

  // One inline section per status (in STATUS_SECTIONS order), each grouped
  // by batch. Statuses with no items are skipped.
  const statusSections = useMemo(
    () =>
      STATUS_SECTIONS.map(section => ({
        ...section,
        items: items.filter(i => i.status === section.status),
      }))
        .filter(section => section.items.length > 0)
        .map(section => ({ ...section, batches: groupByBatch(section.items) })),
    [items],
  )

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

  const redispatchBulkMutation = useMutation({
    mutationFn: (ids: string[]) => reviewApi.redispatchBulk(ids),
    onSuccess: () => {
      setSelected(new Set())
      void queryClient.invalidateQueries({ queryKey: ['review-requests'] })
    },
  })

  // Clone failed/completed rows, then immediately dispatch the clones.
  // Originals stay untouched — full history preserved.
  const retryViaCloneMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      const { created } = await reviewApi.redispatchBulk(ids)
      const newIds = created.map(r => r.id)
      if (newIds.length > 0) {
        await reviewApi.dispatch(newIds)
      }
      return { cloned: created.length, dispatched: newIds.length }
    },
    onSuccess: () => {
      setSelected(new Set())
      void queryClient.invalidateQueries({ queryKey: ['review-requests'] })
    },
  })

  // Sections mix statuses, so the selection can too — route each id to the
  // action its status supports.
  const itemById = useMemo(() => new Map(items.map(i => [i.id, i])), [items])
  const selectedItems = Array.from(selected)
    .map(id => itemById.get(id))
    .filter((i): i is ReviewRequestItem => Boolean(i))
  const pendingIds = selectedItems.filter(i => i.status === 'pending_review').map(i => i.id)
  const retryableIds = selectedItems
    .filter(i => i.status === 'completed' || i.status === 'failed')
    .map(i => i.id)

  return (
    <section id="review-queue" className="flex flex-col">
      <div className="pb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Review Queue</h2>
        <Select
          value={statusFilter}
          onValueChange={v => {
            setStatusFilter(v as ReviewStatus | 'all')
            setSelected(new Set())
          }}
        >
          <SelectTrigger className="h-8 w-[170px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All states</SelectItem>
            {FILTER_STATUSES.map(({ status, label }) => (
              <SelectItem key={status} value={status}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-8">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-12">
            No requests{statusFilter !== 'all' ? ` with status "${statusFilter.replace('_', ' ')}"` : ''}.
          </p>
        ) : (
          statusSections.map(({ status, label, items: sectionItems, batches }) => (
            <section key={status} className="space-y-3">
              <div className="flex items-center gap-2 border-b pb-1.5">
                <h3 className="text-sm font-semibold">{label}</h3>
                <Badge variant={STATUS_BADGE[status]} className="text-xs">
                  {sectionItems.length}
                </Badge>
              </div>
              {batches.map(([batchId, batchItems]) => (
                <div key={batchId} className="space-y-2">
                  <div className="flex items-center gap-3">
                    <h4 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                      Batch {batchId.slice(0, 8)} ({batchItems.length})
                    </h4>
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
                        personas={personas}
                        visionModels={visionModels}
                        loraOptions={loraOptions}
                        imageOptions={refImages.map(i => i.filename)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </section>
          ))
        )}
      </div>

      {selectedItems.length > 0 && (
        <div className="sticky bottom-0 mt-4 border rounded-md bg-card p-3 flex items-center justify-between shadow-sm">
          <p className="text-sm text-muted-foreground">{selectedItems.length} selected</p>
          <div className="flex gap-2">
            {retryableIds.length > 0 && (
              <>
                <Button
                  variant="outline"
                  onClick={() => redispatchBulkMutation.mutate(retryableIds)}
                  disabled={redispatchBulkMutation.isPending}
                >
                  {redispatchBulkMutation.isPending ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Cloning...</>
                  ) : (
                    <><RefreshCcw className="w-4 h-4 mr-2" />Regenerate to pending ({retryableIds.length})</>
                  )}
                </Button>
                <Button
                  onClick={() => retryViaCloneMutation.mutate(retryableIds)}
                  disabled={retryViaCloneMutation.isPending}
                >
                  {retryViaCloneMutation.isPending ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Retrying...</>
                  ) : (
                    <><RotateCcw className="w-4 h-4 mr-2" />Retry selected ({retryableIds.length})</>
                  )}
                </Button>
              </>
            )}
            {pendingIds.length > 0 && (
              <Button
                onClick={() => dispatchMutation.mutate(pendingIds)}
                disabled={dispatchMutation.isPending}
              >
                {dispatchMutation.isPending ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Dispatching...</>
                ) : (
                  <><Send className="w-4 h-4 mr-2" />Generate selected ({pendingIds.length})</>
                )}
              </Button>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
