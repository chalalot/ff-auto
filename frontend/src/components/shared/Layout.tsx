import React from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Grid, Video, Activity, Loader2, BarChart3, Boxes, Settings, Workflow } from 'lucide-react'
import { useActiveTasks } from '@/hooks/useActiveTasks'
import { useFlowCounts } from '@/hooks/useFlowCounts'
import { useVideoQueueCount } from '@/hooks/useVideoQueueCount'
import type { ActiveTask } from '@/types'
import { MemberPickerModal } from '@/components/shared/MemberPickerModal'
import { ProjectSelector } from '@/components/shared/ProjectSelector'
import { Toaster } from '@/components/shared/Toaster'

const TERMINAL = new Set(['SUCCESS', 'FAILURE', 'REVOKED'])

function getWorkerBanner(tasks: ActiveTask[]): { label: string; detail: string } | null {
  const busy = tasks.filter(t => !TERMINAL.has(t.state))
  if (busy.length === 0) return null

  const captionTask = busy.find(t => t.task_type === 'caption_export')
  const processTasks = busy.filter(t => t.task_type === 'image_process')

  const parts: string[] = []
  if (captionTask) {
    const n = captionTask.image_count
    parts.push(n ? `captioning ${n} image${n !== 1 ? 's' : ''}` : 'captioning images')
  }
  if (processTasks.length > 0) {
    parts.push(`generating ${processTasks.length} image${processTasks.length !== 1 ? 's' : ''}`)
  }

  const primaryTask = captionTask ?? busy[0]
  return { label: parts.join(' + '), detail: primaryTask.status_message || '' }
}

const navItems: { to: string; label: string; icon: React.FC<React.SVGProps<SVGSVGElement>>; disabled?: boolean }[] = [
  { to: '/flow', label: 'Flow', icon: Workflow },
  { to: '/library', label: 'Library', icon: Grid },
  // Its own destination, not a Flow stage: it consumes a set of approved images
  // to build a dataset and train a character LoRA.
  { to: '/lora', label: 'LoRA', icon: Boxes },
  { to: '/analysis', label: 'Analysis', icon: BarChart3 },
  { to: '/video', label: 'Video', icon: Video },
  { to: '/monitor', label: 'Monitor', icon: Activity },
  { to: '/configure', label: 'Configure', icon: Settings },
]

export const Layout: React.FC = () => {
  const { data: activeTasks = [] } = useActiveTasks()
  const workerBanner = getWorkerBanner(activeTasks)
  // Two badges, two meanings. Flow's red one is a queue of work blocked on a
  // human. LoRA's green one is material available to train on — nothing is
  // waiting, so it must not read as an alarm.
  const { waiting, approved } = useFlowCounts()
  // Video has its own queue on its own surface, so it carries its own count —
  // Flow's badge is image work only.
  const videoWaiting = useVideoQueueCount()

  return (
    <div className="flex h-screen bg-background">
      <MemberPickerModal />
      <Toaster />
      {/* Sidebar */}
      <aside className="w-16 lg:w-56 flex flex-col border-r bg-card">
        <div className="p-4 border-b">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-primary rounded-md flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-sm">FF</span>
            </div>
            <span className="hidden lg:block font-semibold text-sm">FF Auto</span>
          </div>
        </div>

        <div className="hidden lg:block p-2 border-b">
          <ProjectSelector />
        </div>

        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, label, icon: Icon, disabled }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  disabled && 'opacity-40 pointer-events-none'
                )
              }
            >
              <Icon className="w-5 h-5 shrink-0" />
              <span className="hidden lg:block">{label}</span>
              {to === '/flow' && waiting > 0 && (
                <span
                  title={`${waiting} waiting on you`}
                  className="ml-auto rounded-full bg-red-500/15 px-1.5 text-[11px] font-semibold tabular-nums text-red-700 dark:text-red-400"
                >
                  {waiting}
                </span>
              )}
              {to === '/video' && videoWaiting > 0 && (
                <span
                  title={`${videoWaiting} video prompt${videoWaiting === 1 ? '' : 's'} waiting on you`}
                  className="ml-auto rounded-full bg-red-500/15 px-1.5 text-[11px] font-semibold tabular-nums text-red-700 dark:text-red-400"
                >
                  {videoWaiting}
                </span>
              )}
              {to === '/lora' && approved > 0 && (
                <span
                  title={`${approved} approved images available to train on`}
                  className="ml-auto rounded-full bg-emerald-500/15 px-1.5 text-[11px] font-semibold tabular-nums text-emerald-700 dark:text-emerald-400"
                >
                  {approved}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col min-h-0 min-w-0">
        {workerBanner && (
          <div className="flex items-center gap-2.5 px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 text-amber-700 dark:text-amber-400 text-sm shrink-0">
            <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
            <span className="font-medium">Worker busy</span>
            <span className="text-amber-600/50 dark:text-amber-400/50">—</span>
            <span>{workerBanner.label}</span>
            {workerBanner.detail && (
              <>
                <span className="text-amber-600/30 dark:text-amber-400/30">·</span>
                <span className="text-amber-600/70 dark:text-amber-400/70 truncate">{workerBanner.detail}</span>
              </>
            )}
            <span className="ml-auto text-xs text-amber-600/50 dark:text-amber-400/50 shrink-0">avoid starting new tasks</span>
          </div>
        )}
        <div className="flex-1 overflow-auto">
          {/* Pages are lazy chunks (see App.tsx); keep the shell visible while one loads */}
          <React.Suspense
            fallback={
              <div className="flex items-center justify-center h-full text-muted-foreground">
                <Loader2 className="w-6 h-6 animate-spin" />
              </div>
            }
          >
            <Outlet />
          </React.Suspense>
        </div>
      </main>
    </div>
  )
}
