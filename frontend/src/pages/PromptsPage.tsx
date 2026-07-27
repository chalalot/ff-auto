import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, Save, CheckCircle } from 'lucide-react'

// Global agent prompts (shared across every persona), edited on the System Prompt tab.
const AGENT_FILES = [
  { key: 'agent_system.txt', label: 'System Prompt', description: 'How to analyze the reference and write the Z-Image prompt' },
  { key: 'agent_instruction.txt', label: 'Task Template', description: 'Per-run task instruction: mode, dimensions, brief, identity lock' },
]

const agentPromptApi = {
  getAll: () => apiClient.get<Record<string, string>>('/config/agent-prompts').then(r => r.data),
  save: (filename: string, content: string) =>
    apiClient.put(`/config/agent-prompts/${filename}`, content, {
      headers: { 'Content-Type': 'text/plain' },
    }).then(r => r.data),
}

const identityLockApi = {
  getAll: () => apiClient.get<Record<string, string>>('/config/identity-locks').then(r => r.data),
  save: (name: string, content: string) =>
    apiClient.put(`/config/identity-locks/${encodeURIComponent(name)}`, content, {
      headers: { 'Content-Type': 'text/plain' },
    }).then(r => r.data),
}

// ---------------------------------------------------------------------------
// Top-level page with tab switcher
// ---------------------------------------------------------------------------

const TAB_LABELS: Record<'agent' | 'personas', string> = {
  agent: 'System Prompt',
  personas: 'Personas',
}

export const PromptsPage: React.FC = () => {
  const [tab, setTab] = useState<'agent' | 'personas'>('agent')

  return (
    <div className="flex flex-col h-full">
      {/* Top tab bar */}
      <div className="border-b bg-card px-4 flex items-center gap-0 shrink-0">
        {(['agent', 'personas'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-3 text-sm border-b-2 transition-colors
              ${tab === t
                ? 'border-primary text-foreground font-medium'
                : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-hidden">
        {tab === 'agent' ? <AgentTab /> : <PersonasTab />}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// System Prompt tab — the global single-agent prompts, freely editable
// ---------------------------------------------------------------------------

const AgentTab: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<string>(AGENT_FILES[0].key)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [savedFile, setSavedFile] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: files, isLoading } = useQuery({
    queryKey: ['agent-prompts'],
    queryFn: agentPromptApi.getAll,
  })

  const saveMutation = useMutation({
    mutationFn: ({ filename, content }: { filename: string; content: string }) =>
      agentPromptApi.save(filename, content),
    onSuccess: (_data, { filename }) => {
      queryClient.invalidateQueries({ queryKey: ['agent-prompts'] })
      setSavedFile(filename)
      setEdits(prev => { const next = { ...prev }; delete next[filename]; return next })
      setTimeout(() => setSavedFile(null), 2000)
    },
  })

  const currentContent = edits[selectedFile] ?? (files?.[selectedFile] || '')
  const isDirty = selectedFile in edits
  const fileInfo = AGENT_FILES.find(f => f.key === selectedFile)

  return (
    <div className="flex flex-col h-full">
      <div className="border-b bg-card px-4 flex items-center gap-1 overflow-x-auto">
        {AGENT_FILES.map(f => (
          <button
            key={f.key}
            onClick={() => setSelectedFile(f.key)}
            className={`px-3 py-3 text-sm border-b-2 transition-colors whitespace-nowrap
              ${selectedFile === f.key
                ? 'border-primary text-foreground font-medium'
                : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
          >
            {f.label}
            {f.key in edits && (
              <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-orange-400 inline-block" />
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 flex flex-col overflow-hidden p-4 gap-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-medium">{fileInfo?.label}</span>
            <span className="text-xs text-muted-foreground ml-2">{fileInfo?.description}</span>
            <Badge variant="outline" className="ml-2 text-xs">global</Badge>
          </div>
          <Button
            size="sm"
            disabled={!isDirty || saveMutation.isPending}
            onClick={() => saveMutation.mutate({ filename: selectedFile, content: currentContent })}
          >
            {saveMutation.isPending && saveMutation.variables?.filename === selectedFile ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : savedFile === selectedFile ? (
              <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
            ) : (
              <Save className="w-4 h-4 mr-2" />
            )}
            {savedFile === selectedFile ? 'Saved' : 'Save'}
          </Button>
        </div>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <Textarea
            className="flex-1 font-mono text-sm resize-none min-h-0"
            value={currentContent}
            onChange={e => setEdits(prev => ({ ...prev, [selectedFile]: e.target.value }))}
            placeholder={`Edit ${fileInfo?.label}...`}
          />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Personas tab — one preset identity lock per character (the fixed "who" text
// injected into every generated prompt). Filename = character, content = lock.
// ---------------------------------------------------------------------------

const PersonasTab: React.FC = () => {
  const [selected, setSelected] = useState<string | null>(null)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [savedName, setSavedName] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data: locks, isLoading } = useQuery({
    queryKey: ['identity-locks'],
    queryFn: identityLockApi.getAll,
  })

  const names = React.useMemo(() => Object.keys(locks || {}).sort(), [locks])

  React.useEffect(() => {
    if (names.length > 0 && (!selected || !names.includes(selected))) {
      setSelected(names[0])
    }
  }, [names, selected])

  const saveMutation = useMutation({
    mutationFn: ({ name, content }: { name: string; content: string }) =>
      identityLockApi.save(name, content),
    onSuccess: (_data, { name }) => {
      queryClient.invalidateQueries({ queryKey: ['identity-locks'] })
      queryClient.invalidateQueries({ queryKey: ['persona-instructions', name] })
      setSavedName(name)
      setEdits(prev => { const next = { ...prev }; delete next[name]; return next })
      setTimeout(() => setSavedName(null), 2000)
    },
  })

  const currentContent = selected ? (edits[selected] ?? (locks?.[selected] || '')) : ''
  const isDirty = selected != null && selected in edits

  return (
    <div className="flex h-full">
      <aside className="w-44 border-r bg-card flex flex-col">
        <div className="p-3 border-b">
          <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Characters</h2>
        </div>
        <div className="flex-1 p-2 space-y-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex justify-center pt-4">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : names.length === 0 ? (
            <p className="text-xs text-muted-foreground px-2 pt-2">No characters found.</p>
          ) : (
            names.map(name => (
              <button
                key={name}
                onClick={() => setSelected(name)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors flex items-center justify-between
                  ${selected === name
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  }`}
              >
                <span className="font-mono text-xs">{name}</span>
                {name in edits && (
                  <span className="w-1.5 h-1.5 rounded-full bg-orange-400 inline-block" />
                )}
              </button>
            ))
          )}
        </div>
      </aside>

      <div className="flex-1 flex flex-col overflow-hidden p-4 gap-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-medium">Identity Lock</span>
            <span className="text-xs text-muted-foreground ml-2">
              The fixed "who" text injected verbatim into every prompt for this character
            </span>
            {selected && <Badge variant="outline" className="ml-2 text-xs">{selected}</Badge>}
          </div>
          <Button
            size="sm"
            disabled={!isDirty || saveMutation.isPending}
            onClick={() => selected && saveMutation.mutate({ name: selected, content: currentContent })}
          >
            {saveMutation.isPending && saveMutation.variables?.name === selected ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : savedName === selected ? (
              <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
            ) : (
              <Save className="w-4 h-4 mr-2" />
            )}
            {savedName === selected ? 'Saved' : 'Save'}
          </Button>
        </div>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <Textarea
            className="flex-1 font-mono text-sm resize-none min-h-0"
            value={currentContent}
            onChange={e => selected && setEdits(prev => ({ ...prev, [selected]: e.target.value }))}
            placeholder={selected
              ? 'e.g. a young adult Western woman in her early 20s. She has a typical small rounded oval face, almond-shaped pale eyes and long lashes, fair luminous skin, long voluminous wavy blonde hair'
              : 'Select a character'}
            disabled={!selected}
          />
        )}
      </div>
    </div>
  )
}
