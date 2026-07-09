import React, { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { projectsApi } from '@/api/projects'
import { setProjectId } from '@/lib/identity'

export const CreateProjectModal: React.FC<{
  open: boolean
  onClose: () => void
}> = ({ open, onClose }) => {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  if (!open) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const clean = name.trim()
    if (!clean || busy) return
    setBusy(true)
    try {
      const project = await projectsApi.create(clean)
      await qc.invalidateQueries({ queryKey: ['projects'] })
      setProjectId(project.id) // drop into the new, empty project
      setName('')
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-lg border bg-card p-6 space-y-4">
        <h2 className="font-semibold text-sm">New project</h2>
        <form onSubmit={submit} className="space-y-3">
          <Input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Project name"
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={!name.trim() || busy}>Create</Button>
          </div>
        </form>
      </div>
    </div>
  )
}
