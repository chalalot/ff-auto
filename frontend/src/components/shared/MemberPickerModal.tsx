import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { membersApi } from '@/api/members'
import { getMemberName, setMemberName } from '@/lib/identity'

export const MemberPickerModal: React.FC = () => {
  const [current, setCurrent] = useState(getMemberName())
  const [draft, setDraft] = useState('')
  const { data: members = [] } = useQuery({
    queryKey: ['members'],
    queryFn: membersApi.list,
    enabled: current === null,
  })

  if (current) return null

  const choose = async (name: string) => {
    const clean = name.trim()
    if (!clean) return
    await membersApi.create(clean)
    setMemberName(clean)
    setCurrent(clean)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-lg border bg-card p-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Who's working?</h2>
          <p className="text-sm text-muted-foreground">
            Pick your name — everything you create is tagged with it.
          </p>
        </div>
        {members.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {members.map(m => (
              <Button key={m.id} variant="outline" size="sm" onClick={() => choose(m.name)}>
                {m.name}
              </Button>
            ))}
          </div>
        )}
        <form
          className="flex gap-2"
          onSubmit={e => { e.preventDefault(); void choose(draft) }}
        >
          <Input
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder="Or type a new name"
            autoFocus
          />
          <Button type="submit" disabled={!draft.trim()}>Join</Button>
        </form>
      </div>
    </div>
  )
}
