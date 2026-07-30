import { useSyncExternalStore } from 'react'

export interface ToastMessage {
  id: number
  title: string
  description?: string
  /** A "pull forward" link — the point of the toast is that you don't have to
   *  go looking for what just happened. */
  action?: { label: string; to: string }
  tone?: 'default' | 'error'
}

const DEFAULT_MS = 7000

// A module-level store rather than a context, so mutations in any component
// (or hook) can toast without threading a provider through — same shape as
// lib/identity.ts.
let toasts: ToastMessage[] = []
const listeners = new Set<() => void>()
let nextId = 1

const emit = () => {
  for (const listener of listeners) listener()
}

export const toast = (message: Omit<ToastMessage, 'id'>, durationMs = DEFAULT_MS): number => {
  const id = nextId++
  toasts = [...toasts, { ...message, id }]
  emit()
  if (durationMs > 0) setTimeout(() => dismissToast(id), durationMs)
  return id
}

export const dismissToast = (id: number) => {
  const next = toasts.filter(t => t.id !== id)
  if (next.length === toasts.length) return
  toasts = next
  emit()
}

const subscribe = (cb: () => void) => {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

const getSnapshot = () => toasts

export const useToasts = () => useSyncExternalStore(subscribe, getSnapshot)
