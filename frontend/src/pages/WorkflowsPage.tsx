import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { workflowsApi } from '@/api/workflows'
import { WorkflowGraphForm } from '@/components/workspace/WorkflowGraphForm'
import { WorkflowTagsPanel } from '@/components/workspace/WorkflowTagsPanel'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  AlertTriangle, CheckCircle, Copy, Download, FilePlus2, Loader2,
  Pencil, Save, Trash2, Upload, RotateCcw,
} from 'lucide-react'
import type { WorkflowGraph } from '@/types'

/**
 * Manage the ComfyUI workflow JSON files the generation pipelines build from.
 *
 * The editable state is the JSON *text* (`draft`), not a parsed object: it is
 * the only representation that can hold a half-typed edit, and it keeps the two
 * tabs from drifting. The Parameters tab parses the draft, applies a field edit
 * to the result, and re-serialises — so both tabs always show the same content.
 */

const INDENT = 2
const stringify = (graph: WorkflowGraph) => JSON.stringify(graph, null, INDENT)

/** Pull FastAPI's `detail` out of an axios error, falling back to its message. */
function errorDetail(err: unknown, fallback = 'Request failed'): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  const message = (err as { message?: string })?.message
  return message || fallback
}

type NamePrompt = {
  mode: 'create' | 'rename' | 'duplicate'
  title: string
  description: string
  confirmLabel: string
  initial: string
}

export const WorkflowsPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState<'form' | 'raw' | 'tags'>('form')
  /** Edited JSON text; null means "unchanged from what the server returned". */
  const [draft, setDraft] = useState<string | null>(null)
  const [namePrompt, setNamePrompt] = useState<NamePrompt | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const flash = useCallback((kind: 'ok' | 'error', text: string) => {
    setToast({ kind, text })
    // Errors need reading time; a success just confirms what the user just did.
    window.setTimeout(() => setToast(null), kind === 'ok' ? 2500 : 8000)
  }, [])

  const libraryQuery = useQuery({
    queryKey: ['workflow-library'],
    queryFn: workflowsApi.list,
  })
  const workflows = libraryQuery.data ?? []

  const graphQuery = useQuery({
    queryKey: ['workflow-graph', selected],
    queryFn: () => workflowsApi.getGraph(selected as string),
    enabled: selected != null,
  })

  // Keep a valid selection as the library changes (first load, rename, delete).
  useEffect(() => {
    if (workflows.length === 0) {
      if (selected !== null) setSelected(null)
      return
    }
    if (selected == null || !workflows.some(w => w.name === selected)) {
      setSelected(workflows[0].name)
      setDraft(null)
    }
  }, [workflows, selected])

  /** Refetch the library and the open file, then re-select `name`. */
  const refreshTo = useCallback(
    async (name: string | null) => {
      setDraft(null)
      if (name !== null) setSelected(name)
      await queryClient.invalidateQueries({ queryKey: ['workflow-library'] })
      // The generation selector reads the same directory.
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      if (name !== null) {
        await queryClient.invalidateQueries({ queryKey: ['workflow-graph', name] })
      }
    },
    [queryClient],
  )

  const serverText = graphQuery.data?.raw ?? ''
  const text = draft ?? serverText
  const isDirty = draft !== null && draft !== serverText

  /** Parse the current draft once per change; both tabs read this. */
  const parsed = useMemo((): { graph: WorkflowGraph | null; error: string | null } => {
    if (!text.trim()) return { graph: null, error: 'File is empty.' }
    try {
      const value = JSON.parse(text)
      if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        return { graph: null, error: 'Workflow must be a JSON object of node id → node.' }
      }
      return { graph: value as WorkflowGraph, error: null }
    } catch (err) {
      return { graph: null, error: (err as Error).message }
    }
  }, [text])

  // A file that doesn't parse can only be repaired as text.
  useEffect(() => {
    if (parsed.graph === null && tab === 'form') setTab('raw')
  }, [parsed.graph, tab])

  const saveMutation = useMutation({
    mutationFn: ({ name, graph }: { name: string; graph: WorkflowGraph }) =>
      workflowsApi.save(name, graph),
    onSuccess: async ({ name }) => {
      await refreshTo(name)
      flash('ok', `Saved ${name}`)
    },
    onError: err => flash('error', errorDetail(err, 'Could not save workflow')),
  })

  const createMutation = useMutation({
    mutationFn: (name: string) => workflowsApi.create(name),
    onSuccess: async ({ name }) => {
      await refreshTo(name)
      setTab('form')
      flash('ok', `Created ${name}`)
    },
    onError: err => flash('error', errorDetail(err, 'Could not create workflow')),
  })

  const duplicateMutation = useMutation({
    mutationFn: ({ name, newName }: { name: string; newName?: string }) =>
      workflowsApi.duplicate(name, newName),
    onSuccess: async ({ name }) => {
      await refreshTo(name)
      flash('ok', `Duplicated to ${name}`)
    },
    onError: err => flash('error', errorDetail(err, 'Could not duplicate workflow')),
  })

  const renameMutation = useMutation({
    mutationFn: ({ name, newName }: { name: string; newName: string }) =>
      workflowsApi.rename(name, newName),
    onSuccess: async ({ name }) => {
      await refreshTo(name)
      flash('ok', `Renamed to ${name}`)
    },
    onError: err => flash('error', errorDetail(err, 'Could not rename workflow')),
  })

  const deleteMutation = useMutation({
    mutationFn: (name: string) => workflowsApi.remove(name),
    onSuccess: async ({ name }) => {
      setConfirmDelete(null)
      setSelected(null)
      await refreshTo(null)
      flash('ok', `Deleted ${name}`)
    },
    onError: err => {
      setConfirmDelete(null)
      flash('error', errorDetail(err, 'Could not delete workflow'))
    },
  })

  const importMutation = useMutation({
    mutationFn: (file: File) => workflowsApi.import(file),
    onSuccess: async ({ name }) => {
      await refreshTo(name)
      flash('ok', `Imported ${name}`)
    },
    onError: err => flash('error', errorDetail(err, 'Could not import workflow')),
  })

  const busy =
    saveMutation.isPending || createMutation.isPending || duplicateMutation.isPending ||
    renameMutation.isPending || deleteMutation.isPending || importMutation.isPending

  /** Apply a field edit by rewriting the draft text through the parsed graph. */
  const editGraph = useCallback(
    (mutate: (graph: WorkflowGraph) => void) => {
      if (parsed.graph === null) return
      const next = JSON.parse(JSON.stringify(parsed.graph)) as WorkflowGraph
      mutate(next)
      setDraft(stringify(next))
    },
    [parsed.graph],
  )

  const handleInputChange = useCallback(
    (nodeId: string, key: string, value: unknown) =>
      editGraph(graph => {
        const node = graph[nodeId]
        if (node?.inputs) node.inputs[key] = value
      }),
    [editGraph],
  )

  const handleTitleChange = useCallback(
    (nodeId: string, title: string) =>
      editGraph(graph => {
        const node = graph[nodeId]
        if (!node) return
        if (title.trim()) {
          node._meta = { ...node._meta, title }
        } else if (node._meta) {
          // An empty title means "no title" — drop the key rather than store "".
          const { title: _dropped, ...rest } = node._meta
          if (Object.keys(rest).length > 0) node._meta = rest
          else delete node._meta
        }
      }),
    [editGraph],
  )

  const handleSave = () => {
    if (selected == null || parsed.graph === null) return
    saveMutation.mutate({ name: selected, graph: parsed.graph })
  }

  const handleFormat = () => {
    if (parsed.graph !== null) setDraft(stringify(parsed.graph))
  }

  const handleDownload = () => {
    if (selected == null) return
    const blob = new Blob([text], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = selected
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleNamePromptSubmit = (value: string) => {
    if (!namePrompt) return
    const trimmed = value.trim()
    if (!trimmed) return
    if (namePrompt.mode === 'create') createMutation.mutate(trimmed)
    if (namePrompt.mode === 'duplicate' && selected)
      duplicateMutation.mutate({ name: selected, newName: trimmed })
    if (namePrompt.mode === 'rename' && selected)
      renameMutation.mutate({ name: selected, newName: trimmed })
    setNamePrompt(null)
  }

  const selectWorkflow = (name: string) => {
    if (name === selected) return
    if (isDirty && !window.confirm(`Discard unsaved changes to ${selected}?`)) return
    setDraft(null)
    setSelected(name)
    setTab('form')
  }

  const selectedSummary = workflows.find(w => w.name === selected)

  return (
    <div className="flex h-full">
      {/* ------------------------------------------------------------------ */}
      {/* Library                                                            */}
      {/* ------------------------------------------------------------------ */}
      <aside className="w-64 border-r bg-card flex flex-col shrink-0">
        <div className="p-3 border-b space-y-2">
          <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Workflows
          </h2>
          <div className="flex gap-1.5">
            <Button
              size="sm"
              variant="outline"
              className="flex-1 h-7 text-xs"
              disabled={busy}
              onClick={() =>
                setNamePrompt({
                  mode: 'create',
                  title: 'New workflow',
                  description:
                    'Creates a minimal text-to-image graph you can edit. A .json suffix is added automatically.',
                  confirmLabel: 'Create',
                  initial: '',
                })
              }
            >
              <FilePlus2 className="w-3.5 h-3.5 mr-1" />
              New
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="flex-1 h-7 text-xs"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="w-3.5 h-3.5 mr-1" />
              Import
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={e => {
                const file = e.target.files?.[0]
                if (file) importMutation.mutate(file)
                e.target.value = ''
              }}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {libraryQuery.isLoading ? (
            <div className="flex justify-center pt-4">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : libraryQuery.isError ? (
            <p className="px-2 pt-2 text-xs text-destructive">
              {errorDetail(libraryQuery.error, 'Could not load workflows')}
            </p>
          ) : workflows.length === 0 ? (
            <p className="px-2 pt-2 text-xs text-muted-foreground">
              No workflows yet. Create one, or import a ComfyUI API-format JSON.
            </p>
          ) : (
            workflows.map(wf => (
              <button
                key={wf.name}
                onClick={() => selectWorkflow(wf.name)}
                className={`w-full text-left px-2.5 py-2 rounded-md transition-colors ${
                  selected === wf.name
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-[11px] break-all leading-snug">{wf.name}</span>
                  {selected === wf.name && isDirty && (
                    <span className="w-1.5 h-1.5 rounded-full bg-orange-400 shrink-0" />
                  )}
                </div>
                <div className="flex items-center gap-1.5 mt-0.5 text-[10px] opacity-70">
                  {wf.valid ? (
                    <span>{wf.node_count} nodes</span>
                  ) : (
                    <span className="flex items-center gap-1 text-destructive">
                      <AlertTriangle className="w-3 h-3" />
                      invalid
                    </span>
                  )}
                  <span>·</span>
                  <span>{(wf.size_bytes / 1024).toFixed(1)} KB</span>
                </div>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* ------------------------------------------------------------------ */}
      {/* Editor                                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex-1 flex flex-col min-w-0">
        {selected == null ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">
              Select a workflow, or create one to get started.
            </p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="border-b bg-card px-4 py-2.5 flex items-center gap-2 flex-wrap shrink-0">
              <span className="font-mono text-sm font-medium break-all">{selected}</span>
              {isDirty && (
                <Badge variant="outline" className="text-[10px] text-orange-500 border-orange-500/40">
                  unsaved
                </Badge>
              )}
              {selectedSummary && !selectedSummary.valid && !isDirty && (
                <Badge variant="outline" className="text-[10px] text-destructive border-destructive/40">
                  invalid
                </Badge>
              )}

              <div className="ml-auto flex items-center gap-1.5">
                <Button
                  size="sm" variant="ghost" className="h-7 text-xs" disabled={busy}
                  onClick={() =>
                    setNamePrompt({
                      mode: 'rename', title: 'Rename workflow',
                      description: 'Runs already dispatched are unaffected; saved presets referencing the old name will no longer resolve.',
                      confirmLabel: 'Rename', initial: selected,
                    })
                  }
                >
                  <Pencil className="w-3.5 h-3.5 mr-1" />
                  Rename
                </Button>
                <Button
                  size="sm" variant="ghost" className="h-7 text-xs" disabled={busy}
                  onClick={() =>
                    setNamePrompt({
                      mode: 'duplicate', title: 'Duplicate workflow',
                      description: 'Copies this workflow under a new name.',
                      confirmLabel: 'Duplicate', initial: `${selected.replace(/\.json$/i, '')} copy`,
                    })
                  }
                >
                  <Copy className="w-3.5 h-3.5 mr-1" />
                  Duplicate
                </Button>
                <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={handleDownload}>
                  <Download className="w-3.5 h-3.5 mr-1" />
                  Download
                </Button>
                <Button
                  size="sm" variant="ghost"
                  className="h-7 text-xs text-destructive hover:text-destructive"
                  disabled={busy}
                  onClick={() => setConfirmDelete(selected)}
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  Delete
                </Button>

                <div className="w-px h-5 bg-border mx-0.5" />

                <Button
                  size="sm" variant="outline" className="h-7 text-xs"
                  disabled={!isDirty || busy}
                  onClick={() => setDraft(null)}
                >
                  <RotateCcw className="w-3.5 h-3.5 mr-1" />
                  Discard
                </Button>
                <Button
                  size="sm" className="h-7 text-xs"
                  disabled={!isDirty || parsed.graph === null || busy}
                  isLoading={saveMutation.isPending}
                  onClick={handleSave}
                >
                  <Save className="w-3.5 h-3.5 mr-1" />
                  Save
                </Button>
              </div>
            </div>

            {/* Tabs */}
            <div className="border-b bg-card px-4 flex items-center gap-0 shrink-0">
              {([
                ['form', 'Parameters'],
                ['raw', 'Raw JSON'],
                ['tags', 'Type & inputs'],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  disabled={key === 'form' && parsed.graph === null}
                  className={`px-4 py-2.5 text-sm border-b-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                    tab === key
                      ? 'border-primary text-foreground font-medium'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {label}
                </button>
              ))}
              <div className="ml-auto flex items-center gap-2 text-xs">
                {parsed.error ? (
                  <span className="flex items-center gap-1.5 text-destructive">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate max-w-[380px]">{parsed.error}</span>
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                    valid JSON · {Object.keys(parsed.graph ?? {}).length} nodes
                  </span>
                )}
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-hidden p-4">
              {graphQuery.isLoading ? (
                <div className="h-full flex items-center justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : graphQuery.isError ? (
                <p className="text-sm text-destructive">
                  {errorDetail(graphQuery.error, 'Could not open workflow')}
                </p>
              ) : tab === 'raw' ? (
                <div className="h-full flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">
                      ComfyUI <span className="font-medium">API-format</span> graph — node id → {'{'} class_type, inputs {'}'}.
                    </p>
                    <button
                      className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-40"
                      disabled={parsed.graph === null}
                      onClick={handleFormat}
                    >
                      format
                    </button>
                  </div>
                  <Textarea
                    className="flex-1 font-mono text-xs resize-none min-h-0 leading-relaxed"
                    spellCheck={false}
                    value={text}
                    onChange={e => setDraft(e.target.value)}
                  />
                </div>
              ) : tab === 'tags' ? (
                // Reads the saved graph rather than the draft: a binding must
                // point at a node that is actually on disk for the dispatcher.
                <WorkflowTagsPanel workflowName={selected} graph={graphQuery.data?.graph ?? null} />
              ) : (
                <div className="h-full overflow-y-auto pr-1">
                  {graphQuery.data?.error && !isDirty && (
                    <p className="mb-3 text-xs text-destructive">{graphQuery.data.error}</p>
                  )}
                  {parsed.graph && (
                    <WorkflowGraphForm
                      graph={parsed.graph}
                      onInputChange={handleInputChange}
                      onTitleChange={handleTitleChange}
                    />
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-4 right-4 z-[70] max-w-md rounded-lg px-4 py-2.5 text-sm shadow-lg ${
            toast.kind === 'ok'
              ? 'bg-green-600 text-white'
              : 'bg-destructive text-destructive-foreground'
          }`}
        >
          {toast.text}
        </div>
      )}

      <NamePromptDialog
        prompt={namePrompt}
        isLoading={busy}
        onCancel={() => setNamePrompt(null)}
        onSubmit={handleNamePromptSubmit}
      />

      <ConfirmDialog
        open={confirmDelete !== null}
        title={`Delete ${confirmDelete}?`}
        description="The workflow file is removed from disk. Runs that already used it are unaffected, but new dispatches selecting it will fail."
        confirmLabel="Delete"
        destructive
        isLoading={deleteMutation.isPending}
        onConfirm={() => confirmDelete && deleteMutation.mutate(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  )
}

/** Small filename prompt — the codebase has no dialog primitive with an input. */
const NamePromptDialog: React.FC<{
  prompt: NamePrompt | null
  isLoading: boolean
  onCancel: () => void
  onSubmit: (value: string) => void
}> = ({ prompt, isLoading, onCancel, onSubmit }) => {
  const [value, setValue] = useState('')

  useEffect(() => {
    setValue(prompt?.initial ?? '')
  }, [prompt])

  if (!prompt) return null

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4"
      onClick={e => { if (e.target === e.currentTarget) onCancel() }}
    >
      <form
        className="bg-background rounded-xl shadow-2xl w-full max-w-md p-6"
        onSubmit={e => { e.preventDefault(); onSubmit(value) }}
      >
        <h2 className="text-base font-semibold">{prompt.title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{prompt.description}</p>
        <div className="mt-4 space-y-1">
          <Label className="text-xs">Filename</Label>
          <Input
            autoFocus
            value={value}
            onChange={e => setValue(e.target.value)}
            placeholder="my-workflow.json"
            className="font-mono text-sm"
          />
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={!value.trim()} isLoading={isLoading}>
            {prompt.confirmLabel}
          </Button>
        </div>
      </form>
    </div>
  )
}
