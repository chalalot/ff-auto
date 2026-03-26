import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Loader2, Save, CheckCircle, Plus, AlertTriangle } from 'lucide-react'

const TEMPLATE_FILES = [
  { key: 'turbo_agent.txt', label: 'Turbo Agent', description: 'Agent backstory / persona' },
  { key: 'turbo_framework.txt', label: 'Framework', description: 'Prompt structure rules' },
  { key: 'turbo_constraints.txt', label: 'Constraints', description: 'What to avoid' },
  { key: 'turbo_example.txt', label: 'Example', description: 'Few-shot example output' },
  { key: 'analyst_agent.txt', label: 'Analyst Agent', description: 'Visual analyst backstory' },
  { key: 'analyst_task.txt', label: 'Analyst Task', description: 'Analyst task instructions' },
]

const templateApi = {
  listTypes: () => apiClient.get<string[]>('/config/templates').then(r => r.data),
  getFiles: (type: string) => apiClient.get<Record<string, string>>(`/config/templates/${type}`).then(r => r.data),
  saveFile: (type: string, filename: string, content: string) =>
    apiClient.put(`/config/templates/${type}/${filename}`, content, {
      headers: { 'Content-Type': 'text/plain' },
    }).then(r => r.data),
}

const personaApi = {
  listPersonas: () => apiClient.get<{ name: string; type: string }[]>('/config/personas').then(r => r.data),
  listTypes: () => apiClient.get<string[]>('/config/persona-types').then(r => r.data),
  updateType: (name: string, type: string) =>
    apiClient.put(`/config/personas/${name}`, { type }).then(r => r.data),
  createType: (name: string) =>
    apiClient.post('/config/persona-types', { name }).then(r => r.data),
}

// ---------------------------------------------------------------------------
// Top-level page with tab switcher
// ---------------------------------------------------------------------------

export const PromptsPage: React.FC = () => {
  const [tab, setTab] = useState<'templates' | 'personas'>('templates')

  return (
    <div className="flex flex-col h-full">
      {/* Top tab bar */}
      <div className="border-b bg-card px-4 flex items-center gap-0 shrink-0">
        {(['templates', 'personas'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-3 text-sm border-b-2 transition-colors capitalize
              ${tab === t
                ? 'border-primary text-foreground font-medium'
                : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
          >
            {t === 'templates' ? 'Templates' : 'Personas & Types'}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-hidden">
        {tab === 'templates' ? <TemplatesTab /> : <PersonasTab />}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Templates tab (unchanged logic)
// ---------------------------------------------------------------------------

const TemplatesTab: React.FC = () => {
  const [selectedType, setSelectedType] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<string>(TEMPLATE_FILES[0].key)
  const [savedFile, setSavedFile] = useState<string | null>(null)
  const [savingAll, setSavingAll] = useState(false)
  const [allSaved, setAllSaved] = useState(false)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()

  const { data: types = [], isLoading: typesLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: templateApi.listTypes,
  })

  React.useEffect(() => {
    if (types.length > 0 && !selectedType) setSelectedType(types[0])
  }, [types, selectedType])

  const { data: files, isLoading: filesLoading } = useQuery({
    queryKey: ['templates', selectedType],
    queryFn: () => templateApi.getFiles(selectedType!),
    enabled: !!selectedType,
  })

  const prevType = React.useRef(selectedType)
  React.useEffect(() => {
    if (prevType.current !== selectedType) {
      setEdits({})
      prevType.current = selectedType
    }
  }, [selectedType])

  const saveMutation = useMutation({
    mutationFn: ({ filename, content }: { filename: string; content: string }) =>
      templateApi.saveFile(selectedType!, filename, content),
    onSuccess: (_data, { filename }) => {
      queryClient.invalidateQueries({ queryKey: ['templates', selectedType] })
      setSavedFile(filename)
      setEdits(prev => { const next = { ...prev }; delete next[filename]; return next })
      setTimeout(() => setSavedFile(null), 2000)
    },
  })

  const dirtyCount = Object.keys(edits).length

  const saveAll = async () => {
    if (!selectedType || dirtyCount === 0) return
    setSavingAll(true)
    try {
      await Promise.all(
        Object.entries(edits).map(([filename, content]) =>
          templateApi.saveFile(selectedType, filename, content)
        )
      )
      setEdits({})
      queryClient.invalidateQueries({ queryKey: ['templates', selectedType] })
      setAllSaved(true)
      setTimeout(() => setAllSaved(false), 2000)
    } finally {
      setSavingAll(false)
    }
  }

  const currentContent = edits[selectedFile] ?? (files?.[selectedFile] || '')
  const isDirty = selectedFile in edits
  const fileInfo = TEMPLATE_FILES.find(f => f.key === selectedFile)

  return (
    <div className="flex h-full">
      <aside className="w-44 border-r bg-card flex flex-col">
        <div className="p-3 border-b">
          <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Types</h2>
        </div>
        <div className="flex-1 p-2 space-y-1">
          {typesLoading ? (
            <div className="flex justify-center pt-4">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : (
            types.map(type => (
              <button
                key={type}
                onClick={() => { setSelectedType(type); setEdits({}) }}
                className={`w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors
                  ${selectedType === type
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  }`}
              >
                {type}
              </button>
            ))
          )}
        </div>
      </aside>

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="border-b bg-card px-4 flex items-center gap-1 overflow-x-auto">
          {TEMPLATE_FILES.map(f => (
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
              {selectedType && (
                <Badge variant="outline" className="ml-2 text-xs">{selectedType}</Badge>
              )}
            </div>
            <div className="flex items-center gap-2">
              {dirtyCount > 1 && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={savingAll}
                  onClick={saveAll}
                >
                  {savingAll ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : allSaved ? (
                    <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
                  ) : (
                    <Save className="w-4 h-4 mr-2" />
                  )}
                  {allSaved ? 'All Saved' : `Save All (${dirtyCount})`}
                </Button>
              )}
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
          </div>

          {filesLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <Textarea
              className="flex-1 font-mono text-sm resize-none min-h-0"
              value={currentContent}
              onChange={e => setEdits(prev => ({ ...prev, [selectedFile]: e.target.value }))}
              placeholder={selectedType ? `Enter ${fileInfo?.label} for ${selectedType}...` : 'Select a type'}
              disabled={!selectedType}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Personas & Types tab
// ---------------------------------------------------------------------------

const PersonasTab: React.FC = () => {
  const [newTypeName, setNewTypeName] = useState('')
  const queryClient = useQueryClient()

  const { data: personas = [], isLoading: personasLoading } = useQuery({
    queryKey: ['personas'],
    queryFn: personaApi.listPersonas,
  })

  const { data: personaTypes = [], isLoading: typesLoading } = useQuery({
    queryKey: ['persona-types'],
    queryFn: personaApi.listTypes,
  })

  // Template types = types that actually have a templates/ directory
  const { data: templateTypes = [] } = useQuery({
    queryKey: ['templates'],
    queryFn: templateApi.listTypes,
  })

  const createTypeMutation = useMutation({
    mutationFn: personaApi.createType,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['persona-types'] })
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      setNewTypeName('')
    },
  })

  const updateTypeMutation = useMutation({
    mutationFn: ({ name, type }: { name: string; type: string }) =>
      personaApi.updateType(name, type),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personas'] })
    },
  })

  const isLoading = personasLoading || typesLoading

  // Group personas by type for the sanity check
  const byType = personaTypes.reduce<Record<string, string[]>>((acc, t) => {
    acc[t] = personas.filter(p => p.type === t).map(p => p.name)
    return acc
  }, {})
  const unassigned = personas.filter(p => !personaTypes.includes(p.type))

  return (
    <div className="p-6 overflow-y-auto h-full space-y-8 max-w-3xl">

      {/* Create new type */}
      <section>
        <h2 className="text-sm font-semibold mb-3">Persona Types</h2>
        <div className="flex flex-wrap gap-2 mb-4">
          {typesLoading ? (
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          ) : (
            personaTypes.map(t => (
              <Badge
                key={t}
                variant={templateTypes.includes(t) ? 'secondary' : 'outline'}
                className="text-xs"
              >
                {t}
                {!templateTypes.includes(t) && (
                  <AlertTriangle className="w-3 h-3 ml-1 text-yellow-500" />
                )}
              </Badge>
            ))
          )}
        </div>
        <div className="flex gap-2 items-center">
          <Input
            placeholder="New type name (e.g. dancer)"
            value={newTypeName}
            onChange={e => setNewTypeName(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && newTypeName.trim()) {
                createTypeMutation.mutate(newTypeName.trim())
              }
            }}
            className="h-8 text-sm w-60"
          />
          <Button
            size="sm"
            disabled={!newTypeName.trim() || createTypeMutation.isPending}
            onClick={() => createTypeMutation.mutate(newTypeName.trim())}
          >
            {createTypeMutation.isPending
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <Plus className="w-4 h-4 mr-1" />
            }
            Create
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Creating a type also scaffolds the template files under Templates tab.
          <AlertTriangle className="w-3 h-3 inline ml-1 text-yellow-500" /> = type exists but has no templates directory yet.
        </p>
      </section>

      {/* Persona → type assignments */}
      <section>
        <h2 className="text-sm font-semibold mb-3">Persona Assignments</h2>
        {isLoading ? (
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        ) : personas.length === 0 ? (
          <p className="text-sm text-muted-foreground">No personas found.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="pb-2 font-medium w-1/3">Persona</th>
                <th className="pb-2 font-medium w-1/3">Type</th>
                <th className="pb-2 font-medium">Template status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {personas.map(p => {
                const hasTemplates = templateTypes.includes(p.type)
                const typeKnown = personaTypes.includes(p.type)
                return (
                  <tr key={p.name} className="h-10">
                    <td className="pr-4 font-mono text-xs">{p.name}</td>
                    <td className="pr-4">
                      <select
                        value={p.type}
                        onChange={e => updateTypeMutation.mutate({ name: p.name, type: e.target.value })}
                        className="bg-background border border-input rounded-md px-2 py-1 text-xs h-7 focus:outline-none focus:ring-1 focus:ring-ring"
                      >
                        {personaTypes.map(t => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                        {/* Keep current value if it's not in the known types list */}
                        {!typeKnown && (
                          <option value={p.type}>{p.type} (unknown)</option>
                        )}
                      </select>
                    </td>
                    <td>
                      {hasTemplates ? (
                        <span className="flex items-center gap-1 text-xs text-green-600">
                          <CheckCircle className="w-3.5 h-3.5" /> Templates exist
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-yellow-600">
                          <AlertTriangle className="w-3.5 h-3.5" /> No templates
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* Sanity check: type → personas breakdown */}
      <section>
        <h2 className="text-sm font-semibold mb-3">Sanity Check — Type → Personas</h2>
        <div className="space-y-3">
          {personaTypes.map(t => (
            <div key={t} className="flex items-start gap-3">
              <Badge variant="outline" className="text-xs mt-0.5 shrink-0 w-28 justify-center">{t}</Badge>
              <div className="flex flex-wrap gap-1.5">
                {byType[t]?.length ? (
                  byType[t].map(name => (
                    <span key={name} className="text-xs bg-muted px-2 py-0.5 rounded font-mono">{name}</span>
                  ))
                ) : (
                  <span className="text-xs text-muted-foreground italic">no personas</span>
                )}
              </div>
            </div>
          ))}
          {unassigned.length > 0 && (
            <div className="flex items-start gap-3">
              <Badge variant="destructive" className="text-xs mt-0.5 shrink-0 w-28 justify-center">unknown type</Badge>
              <div className="flex flex-wrap gap-1.5">
                {unassigned.map(p => (
                  <span key={p.name} className="text-xs bg-muted px-2 py-0.5 rounded font-mono">{p.name}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
