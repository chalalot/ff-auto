import React from 'react'
import * as ToastPrimitive from '@radix-ui/react-toast'
import { Link } from 'react-router-dom'
import { ArrowRight, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { dismissToast, useToasts } from '@/hooks/useToast'

// Mounted once in Layout. Dispatching work no longer navigates away, so this is
// how the user learns something moved along — and how they follow it if they
// want to.
export const Toaster: React.FC = () => {
  const toasts = useToasts()

  return (
    <ToastPrimitive.Provider swipeDirection="right" duration={Infinity}>
      {toasts.map(t => (
        <ToastPrimitive.Root
          key={t.id}
          open
          onOpenChange={open => { if (!open) dismissToast(t.id) }}
          className={cn(
            'flex items-start gap-3 rounded-md border bg-card p-3 shadow-lg',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out',
            'data-[state=open]:animate-in data-[state=open]:slide-in-from-right',
            t.tone === 'error' && 'border-destructive/40',
          )}
        >
          <div className="min-w-0 flex-1 space-y-0.5">
            <ToastPrimitive.Title
              className={cn('text-sm font-medium', t.tone === 'error' && 'text-destructive')}
            >
              {t.title}
            </ToastPrimitive.Title>
            {t.description && (
              <ToastPrimitive.Description className="text-xs text-muted-foreground">
                {t.description}
              </ToastPrimitive.Description>
            )}
            {t.action && (
              <ToastPrimitive.Action asChild altText={t.action.label}>
                <Link
                  to={t.action.to}
                  onClick={() => dismissToast(t.id)}
                  className="inline-flex items-center gap-1 pt-1 text-xs font-medium text-primary hover:underline"
                >
                  {t.action.label}
                  <ArrowRight className="h-3 w-3" aria-hidden="true" />
                </Link>
              </ToastPrimitive.Action>
            )}
          </div>
          <ToastPrimitive.Close
            aria-label="Dismiss"
            className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </ToastPrimitive.Close>
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[60] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  )
}
