import React from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Image, Grid, Video, Activity, FileText, Settings, Archive } from 'lucide-react'

const navItems: { to: string; label: string; icon: React.FC<React.SVGProps<SVGSVGElement>>; disabled?: boolean }[] = [
  { to: '/workspace', label: 'Workspace', icon: Image },
  { to: '/gallery', label: 'Gallery', icon: Grid },
  { to: '/archive', label: 'Archive', icon: Archive },
  { to: '/video', label: 'Video', icon: Video },
  { to: '/monitor', label: 'Monitor', icon: Activity },
  { to: '/prompts', label: 'Prompts', icon: FileText },
]

export const Layout: React.FC = () => {
  return (
    <div className="flex h-screen bg-background">
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
            </NavLink>
          ))}
        </nav>

        <div className="p-2 border-t">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )
            }
          >
            <Settings className="w-5 h-5 shrink-0" />
            <span className="hidden lg:block">Settings</span>
          </NavLink>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
