import { useSyncExternalStore } from 'react'
import { getProjectId, subscribeIdentity } from '@/lib/identity'

/** Active project id from the identity store, or null for the global view. */
export function useProjectId(): string | null {
  return useSyncExternalStore(subscribeIdentity, getProjectId)
}
