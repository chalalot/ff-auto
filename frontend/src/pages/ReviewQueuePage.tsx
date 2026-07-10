import React, { useMemo, useState, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, RefreshCcw, RotateCcw, Send, Trash2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { reviewApi } from '@/api/review'
import { projectsApi } from '@/api/projects'
import { workspaceApi } from '@/api/workspace'
import { useProjectId } from '@/hooks/useProjectId'
import { usePersonas, useVisionModels, useLoraOptions } from '@/hooks/usePersonas'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { WorkflowParametersPanel, buildInitialOverrides, loraShortLabel } from '@/components/workspace/WorkflowParametersPanel'
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
  personas?: PersonaSummary[]
  visionModels?: SelectOption[]
  loraOptions?: string[]
}> = ({
  item,
  checked,
  onToggle,
  projectName,
  personas = [],
  visionModels = [],
  loraOptions = [],
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

  // Local settings state for fast numeric typing — saved on blur.
  const initSettings = useCallback(() => {
    const s: Record<string, string> = {
      base_seed: settingsObj.base_seed != null ? String(settingsObj.base_seed) : '0',
      strength_model: settingsObj.strength_model != null ? String(settingsObj.strength_model) : '1',
      width: settingsObj.width != null ? String(settingsObj.width) : '1024',
      height: settingsObj.height != null ? String(settingsObj.height) : '1024',
    }
    return s
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id, item.updated_at])
  const [localSettings, setLocalSettings] = useState(initSettings)

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

  const saveSettingsField = (key: 'base_seed' | 'strength_model' | 'width' | 'height') => {
    if (!editable) return
    const raw = localSettings[key]
    const original = settingsObj[key]
    let value: unknown = raw
    if (key === 'strength_model') value = raw === '' ? undefined : parseFloat(raw)
    else value = raw === '' ? undefined : parseInt(raw, 10)
    if (String(value ?? '') !== String(original ?? '')) {
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
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
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

              {/* Workflow Type */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Workflow Type
                </label>
                <Select
                  value={String(settingsObj.workflow_type || 'turbo')}
                  onValueChange={v => saveSettingSelect('workflow_type', v)}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="turbo">Turbo</SelectItem>
                    <SelectItem value="normal">Normal</SelectItem>
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

              {/* LoRA */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  LoRA
                </label>
                <Select
                  value={String(settingsObj.lora_name || 'none')}
                  onValueChange={v => saveSettingSelect('lora_name', v === 'none' ? '' : v)}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue placeholder="Select LoRA">
                      {settingsObj.lora_name
                        ? loraShortLabel(String(settingsObj.lora_name))
                        : 'None'}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">
                      <span className="text-muted-foreground">None</span>
                    </SelectItem>
                    {Array.from(
                      new Set([
                        ...(settingsObj.lora_name ? [String(settingsObj.lora_name)] : []),
                        ...loraOptions,
                      ])
                    ).map(
                      l =>
                        l && (
                          <SelectItem key={l} value={l}>
                            <span className="font-medium">{loraShortLabel(l)}</span>
                          </SelectItem>
                        )
                    )}
                  </SelectContent>
                </Select>
              </div>

              {/* Seed Strategy */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Seed Strategy
                </label>
                <Select
                  value={String(settingsObj.seed_strategy || 'random')}
                  onValueChange={v => saveSettingSelect('seed_strategy', v)}
                >
                  <SelectTrigger className="h-7 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="random">Random</SelectItem>
                    <SelectItem value="fixed">Fixed</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Base Seed */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Base Seed
                </label>
                <Input
                  type="number"
                  value={localSettings.base_seed}
                  onChange={e =>
                    setLocalSettings(p => ({ ...p, base_seed: e.target.value }))
                  }
                  onBlur={() => saveSettingsField('base_seed')}
                  className="h-7 text-xs font-mono"
                  placeholder="0"
                />
              </div>

              {/* Strength */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Strength
                </label>
                <Input
                  type="number"
                  step="0.05"
                  value={localSettings.strength_model}
                  onChange={e =>
                    setLocalSettings(p => ({ ...p, strength_model: e.target.value }))
                  }
                  onBlur={() => saveSettingsField('strength_model')}
                  className="h-7 text-xs font-mono"
                  placeholder="1.0"
                />
              </div>

              {/* Width */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Width
                </label>
                <Input
                  type="number"
                  value={localSettings.width}
                  onChange={e =>
                    setLocalSettings(p => ({ ...p, width: e.target.value }))
                  }
                  onBlur={() => saveSettingsField('width')}
                  className="h-7 text-xs font-mono"
                  placeholder="1024"
                />
              </div>

              {/* Height */}
              <div className="space-y-0.5">
                <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
                  Height
                </label>
                <Input
                  type="number"
                  value={localSettings.height}
                  onChange={e =>
                    setLocalSettings(p => ({ ...p, height: e.target.value }))
                  }
                  onBlur={() => saveSettingsField('height')}
                  className="h-7 text-xs font-mono"
                  placeholder="1024"
                />
              </div>
            </div>

            {item.workflow_name && (
              <details className="rounded border border-border/60 px-2.5 py-1.5 bg-muted/20">
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
                  Workflow Parameters ({item.workflow_name.replace(/\.json$/i, '')})
                </summary>
                <div className="mt-2.5 pt-2 border-t border-border/40">
                  <WorkflowParametersPanel
                    params={workflowParams}
                    loading={paramsLoading}
                    error={paramsError ? 'Failed to load parameters' : null}
                    loraOptions={loraOptions}
                    values={currentOverrides}
                    onChange={handleOverrideChange}
                    onReset={() => {
                      if (workflowParams) {
                        const reset = buildInitialOverrides(workflowParams)
                        settingsMutation.mutate({ workflow_overrides: reset })
                      }
                    }}
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

export const ReviewQueuePage: React.FC = () => {
  const projectId = useProjectId() ?? undefined
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

  const { data: personas = [] } = usePersonas()
  const { data: visionModels = [] } = useVisionModels()
  const { data: loraOptions = [] } = useLoraOptions()

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

  const selectedIds = Array.from(selected)
  const showRedispatch = statusFilter === 'completed' || statusFilter === 'failed'

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
                    personas={personas}
                    visionModels={visionModels}
                    loraOptions={loraOptions}
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
          <div className="flex gap-2">
            {showRedispatch && (
              <Button
                variant="outline"
                onClick={() => redispatchBulkMutation.mutate(selectedIds)}
                disabled={redispatchBulkMutation.isPending}
              >
                {redispatchBulkMutation.isPending ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Cloning...</>
                ) : (
                  <><RefreshCcw className="w-4 h-4 mr-2" />Regenerate to pending ({selectedIds.length})</>
                )}
              </Button>
            )}
            {showRedispatch ? (
              <Button
                onClick={() => retryViaCloneMutation.mutate(selectedIds)}
                disabled={retryViaCloneMutation.isPending}
              >
                {retryViaCloneMutation.isPending ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Retrying...</>
                ) : (
                  <><RotateCcw className="w-4 h-4 mr-2" />Retry selected ({selectedIds.length})</>
                )}
              </Button>
            ) : (
              <Button
                onClick={() => dispatchMutation.mutate(selectedIds)}
                disabled={dispatchMutation.isPending}
              >
                {dispatchMutation.isPending ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Dispatching...</>
                ) : (
                  <><Send className="w-4 h-4 mr-2" />Generate selected ({selectedIds.length})</>
                )}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
