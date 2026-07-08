import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Archive, FolderOpen, Loader2, Plus } from 'lucide-react'
import { projectsApi } from '@/api/projects'
import { getProjectId, setProjectId } from '@/lib/identity'

export const ProjectsPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['projects'] })
  const createMutation = useMutation({
    mutationFn: (n: string) => projectsApi.create(n),
    onSuccess: () => { setName(''); invalidate() },
  })
  const archiveMutation = useMutation({
    mutationFn: (id: string) => projectsApi.patch(id, { archived: true }),
    onSuccess: (_data, id) => {
      if (getProjectId() === id) setProjectId(null)
      invalidate()
    },
  })

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold">Projects</h1>
        <form
          className="flex gap-2"
          onSubmit={e => { e.preventDefault(); if (name.trim()) createMutation.mutate(name.trim()) }}
        >
          <Input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="New project name"
            className="w-56"
          />
          <Button type="submit" disabled={!name.trim() || createMutation.isPending}>
            <Plus className="w-4 h-4 mr-2" />Create
          </Button>
        </form>
      </div>
      <div className="flex-1 overflow-auto p-4">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : projects.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-12">
            No projects yet. Create one to start grouping your work.
          </p>
        ) : (
          <div className="space-y-2">
            {projects.map(p => (
              <div key={p.id} className="flex items-center gap-3 rounded-md border p-3">
                <FolderOpen className="w-5 h-5 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <Link to={`/projects/${p.id}`} className="font-medium hover:underline">
                    {p.name}
                  </Link>
                  {p.description && (
                    <p className="text-sm text-muted-foreground truncate">{p.description}</p>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {p.member_ids.length} member{p.member_ids.length !== 1 ? 's' : ''}
                </span>
                <Button
                  variant="ghost" size="icon" title="Archive"
                  onClick={() => archiveMutation.mutate(p.id)}
                >
                  <Archive className="w-4 h-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
