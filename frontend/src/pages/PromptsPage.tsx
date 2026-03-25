import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api-client'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, Save, CheckCircle } from 'lucide-react'

const TEMPLATE_FILES = [
  { key: 'turbo_prompt_template.txt', label: 'Prompt Template', description: 'Main output template' },
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

export const PromptsPage: React.FC = () => {
  const [selectedType, setSelectedType] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<string>(TEMPLATE_FILES[0].key)
  const [savedFile, setSavedFile] = useState<string | null>(null)
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

  // Clear local edits when switching type (new files loaded)
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

  const currentContent = edits[selectedFile] ?? (files?.[selectedFile] || '')
  const isDirty = selectedFile in edits

  const fileInfo = TEMPLATE_FILES.find(f => f.key === selectedFile)

  return (
    <div className="flex h-full">
      {/* Type list */}
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

      {/* File tabs + editor */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* File tabs */}
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

        {/* Editor area */}
        <div className="flex-1 flex flex-col overflow-hidden p-4 gap-3">
          {/* Header row */}
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm font-medium">{fileInfo?.label}</span>
              <span className="text-xs text-muted-foreground ml-2">{fileInfo?.description}</span>
              {selectedType && (
                <Badge variant="outline" className="ml-2 text-xs">{selectedType}</Badge>
              )}
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

          {/* Textarea */}
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
