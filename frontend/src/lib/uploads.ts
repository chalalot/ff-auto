// Drag-and-drop → File resolution and upload error extraction, shared by
// CreatePanel and CaptionExportTab.
import { workspaceApi } from '@/api/workspace'

const DROPPED_MIME_TO_EXT: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
}

// Dragging an image from another web page yields a URL or data: URI rather
// than a File — pull image URLs out of whatever the source put on the drag.
const extractDroppedImageUrls = (dt: DataTransfer): string[] => {
  const html = dt.getData('text/html')
  if (html) {
    const srcs = Array.from(new DOMParser().parseFromString(html, 'text/html').querySelectorAll('img'))
      .map(img => img.getAttribute('src') ?? '')
      .filter(src => /^(https?:|data:image\/)/i.test(src))
    if (srcs.length) return srcs
  }
  const uriList = dt.getData('text/uri-list')
  if (uriList) {
    const urls = uriList.split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith('#'))
    if (urls.length) return urls
  }
  const text = dt.getData('text/plain').trim()
  if (/^(https?:|data:image\/)/i.test(text)) return [text]
  return []
}

const dataUrlToFile = (dataUrl: string): File | null => {
  const match = dataUrl.match(/^data:(image\/[a-z0-9.+-]+);base64,(.+)$/i)
  if (!match) return null
  const mime = match[1].toLowerCase()
  const ext = DROPPED_MIME_TO_EXT[mime]
  if (!ext) return null
  const bytes = Uint8Array.from(atob(match[2]), c => c.charCodeAt(0))
  return new File([bytes], `dropped.${ext}`, { type: mime })
}

const filenameFromUrl = (url: string, ext: string): string => {
  try {
    const stem = (new URL(url).pathname.split('/').pop() ?? '').replace(/\.[a-z0-9]+$/i, '')
    if (stem) return `${stem}.${ext}`
  } catch { /* malformed URL — fall through */ }
  return `dropped.${ext}`
}

// Resolve a drop into File objects: real files pass through untouched, data:
// URIs are decoded locally, and http(s) URLs are downloaded via the backend
// (fetching them from the browser is blocked by CORS on most image hosts).
// Must be CALLED synchronously from the drop handler — DataTransfer contents
// are only readable during the event tick, and this reads them before its
// first await.
export const resolveDroppedFiles = async (dt: DataTransfer): Promise<File[]> => {
  if (dt.files.length > 0) return Array.from(dt.files)
  const urls = extractDroppedImageUrls(dt)
  const files: File[] = []
  for (const url of urls) {
    if (url.startsWith('data:')) {
      const file = dataUrlToFile(url)
      if (file) files.push(file)
      continue
    }
    const blob = await workspaceApi.fetchImageFromUrl(url)
    const ext = DROPPED_MIME_TO_EXT[blob.type] ?? 'png'
    files.push(new File([blob], filenameFromUrl(url, ext), { type: blob.type }))
  }
  return files
}

export const uploadErrorMessage = (err: unknown, fallback = 'Upload failed'): string => {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  if (detail) return detail
  return err instanceof Error ? err.message : fallback
}
