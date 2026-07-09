import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Plus, Settings2 } from 'lucide-react'
import { projectsApi } from '@/api/projects'
import { useProjectId } from '@/hooks/useProjectId'
import { setProjectId } from '@/lib/identity'
import { CreateProjectModal } from '@/components/shared/CreateProjectModal'

const NONE = '__none__'
const CREATE = '__create__'
const MANAGE = '__manage__'

export const ProjectSelector: React.FC = () => {
  const navigate = useNavigate()
  const projectId = useProjectId()
  const [showCreate, setShowCreate] = useState(false)
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  const handleChange = (v: string) => {
    if (v === CREATE) { setShowCreate(true); return }
    if (v === MANAGE) { navigate('/projects'); return }
    // Select the project (or clear to global). No navigation — the current
    // page re-scopes in place via useProjectId.
    setProjectId(v === NONE ? null : v)
  }

  return (
    <>
      <Select value={projectId ?? NONE} onValueChange={handleChange}>
        <SelectTrigger className="w-full text-xs">
          <SelectValue placeholder="No project" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>No project (global)</SelectItem>
          {projects.map(p => (
            <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
          ))}
          <div className="my-1 h-px bg-border" />
          <SelectItem value={CREATE}>
            <span className="flex items-center gap-2"><Plus className="w-3.5 h-3.5" />New project</span>
          </SelectItem>
          <SelectItem value={MANAGE}>
            <span className="flex items-center gap-2"><Settings2 className="w-3.5 h-3.5" />Manage projects…</span>
          </SelectItem>
        </SelectContent>
      </Select>
      <CreateProjectModal open={showCreate} onClose={() => setShowCreate(false)} />
    </>
  )
}
