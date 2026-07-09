import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Archive, FolderOpen, Images, Loader2, Plus } from 'lucide-react'
import { projectsApi } from '@/api/projects'
import { getProjectId, setProjectId } from '@/lib/identity'
import { CreateProjectModal } from '@/components/shared/CreateProjectModal'
import { AssetsPanel } from '@/components/workspace/AssetsPanel'

export const ProjectsPage: React.FC = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [assetsFor, setAssetsFor] = useState<string | null>(null)
  const openProject = (id: string) => { setProjectId(id); navigate('/gallery') }
  const toggleAssets = (id: string) => setAssetsFor(prev => (prev === id ? null : id))
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  const archiveMutation = useMutation({
    mutationFn: (id: string) => projectsApi.patch(id, { archived: true }),
    onSuccess: (_data, id) => {
      if (getProjectId() === id) setProjectId(null)
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold">Projects</h1>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-2" />New project
        </Button>
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
              <div key={p.id} className="rounded-md border">
                <div className="flex items-center gap-3 p-3">
                  <FolderOpen className="w-5 h-5 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <button
                      type="button"
                      onClick={() => openProject(p.id)}
                      className="font-medium hover:underline text-left"
                    >
                      {p.name}
                    </button>
                    {p.description && (
                      <p className="text-sm text-muted-foreground truncate">{p.description}</p>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {p.member_ids.length} member{p.member_ids.length !== 1 ? 's' : ''}
                  </span>
                  <Button
                    variant={assetsFor === p.id ? 'secondary' : 'ghost'} size="icon"
                    title="Assets" onClick={() => toggleAssets(p.id)}
                  >
                    <Images className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="ghost" size="icon" title="Archive"
                    onClick={() => archiveMutation.mutate(p.id)}
                  >
                    <Archive className="w-4 h-4" />
                  </Button>
                </div>
                {assetsFor === p.id && (
                  <div className="border-t bg-muted/30">
                    <AssetsPanel projectId={p.id} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      <CreateProjectModal open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  )
}
