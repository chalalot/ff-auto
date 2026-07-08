import React, { useSyncExternalStore } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { projectsApi } from '@/api/projects'
import { getProjectId, setProjectId, subscribeIdentity } from '@/lib/identity'

const NONE = '__none__'

export const ProjectSelector: React.FC = () => {
  const navigate = useNavigate()
  const projectId = useSyncExternalStore(subscribeIdentity, getProjectId)
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  const handleChange = (v: string) => {
    const id = v === NONE ? null : v
    setProjectId(id)
    if (id) navigate(`/projects/${id}`)
  }

  return (
    <Select
      value={projectId ?? NONE}
      onValueChange={handleChange}
    >
      <SelectTrigger className="w-full text-xs">
        <SelectValue placeholder="No project" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>No project</SelectItem>
        {projects.map(p => (
          <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
