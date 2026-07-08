import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, RotateCcw, Send, Trash2 } from 'lucide-react'
import { reviewApi } from '@/api/review'
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

function settingsSummary(settings: Record<string, unknown>): string {
  return Object.entries(settings)
    .filter(([k, v]) => v != null && v !== '' && k !== 'workflow_overrides' && k !== 'negative_prompt')
    .map(([k, v]) => `${k}=${String(v)}`)
    .join(' · ')
}

const RequestRow: React.FC<{
  item: ReviewRequestItem
  checked: boolean
  onToggle: (id: string) => void
}> = ({ item, checked, onToggle }) => {
  const queryClient = useQueryClient()
  const [prompt, setPrompt] = useState(item.prompt)
  const editable = item.status === 'pending_review'

  const patchMutation = useMutation({
    mutationFn: () => reviewApi.updateRequest(item.id, { prompt }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })
  const discardMutation = useMutation({
    mutationFn: () => reviewApi.discardRequest(item.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })

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
          <span className="text-xs text-muted-foreground truncate">
            {item.source_image_path.split('/').pop()}
          </span>
        </div>
        <Textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onBlur={() => { if (editable && prompt !== item.prompt) patchMutation.mutate() }}
          disabled={!editable}
          rows={3}
          className="text-sm"
        />
        {prompt !== item.original_prompt && (
          <p className="text-xs text-muted-foreground">edited (original kept)</p>
        )}
        <p className="text-xs text-muted-foreground truncate">
          {settingsSummary(item.settings)}
        </p>
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

export const ReviewQueuePage: React.FC = () => {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | 'all'>('pending_review')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['review-requests', statusFilter],
    queryFn: () =>
      reviewApi.listRequests({
        status: statusFilter === 'all' ? undefined : statusFilter,
        per_page: 200,
      }),
    refetchInterval: 5000,
  })

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
