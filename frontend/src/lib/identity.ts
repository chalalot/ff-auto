// localStorage-backed identity. Sent as headers on every API call (see
// api-client.ts); components re-render via the subscribe mechanism.
const MEMBER_KEY = 'ff.memberName'
const PROJECT_KEY = 'ff.projectId'

const listeners = new Set<() => void>()

function notify() {
  listeners.forEach(fn => fn())
}

export function getMemberName(): string | null {
  return localStorage.getItem(MEMBER_KEY)
}

export function setMemberName(name: string): void {
  localStorage.setItem(MEMBER_KEY, name.trim())
  notify()
}

export function getProjectId(): string | null {
  return localStorage.getItem(PROJECT_KEY)
}

export function setProjectId(id: string | null): void {
  if (id) localStorage.setItem(PROJECT_KEY, id)
  else localStorage.removeItem(PROJECT_KEY)
  notify()
}

export function subscribeIdentity(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}
