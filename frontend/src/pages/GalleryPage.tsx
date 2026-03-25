import React, { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import {
  useGalleryImages, useGalleryStats,
  useApproveImages, useDisapproveImages, useUndoImages
} from '@/hooks/useGalleryImages'
import { galleryApi, type GalleryStatus } from '@/api/gallery'
import { formatDistanceToNow } from 'date-fns'
import {
  CheckCircle, XCircle, RotateCcw, Download, RefreshCw,
  Image as ImageIcon, Loader2, ChevronLeft, ChevronRight,
  LayoutGrid, Info, X
} from 'lucide-react'
import type { ImageMetadata } from '@/types'
import type { GalleryImage } from '@/types'

const ITEMS_PER_PAGE = 20

export const GalleryPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<GalleryStatus>('pending')
  const [page, setPage] = useState(1)
  const [selectedImages, setSelectedImages] = useState<Set<string>>(new Set())
  const [renameMap, setRenameMap] = useState<Record<string, string>>({})
  const [columns, setColumns] = useState(4)

  const { data: gallery, isLoading, refetch } = useGalleryImages(activeTab, page, ITEMS_PER_PAGE)
  const { data: stats } = useGalleryStats()
  const approveMutation = useApproveImages()
  const disapproveMutation = useDisapproveImages()
  const undoMutation = useUndoImages()

  const handleTabChange = (tab: string) => {
    setActiveTab(tab as GalleryStatus)
    setPage(1)
    setSelectedImages(new Set())
    setRenameMap({})
  }

  const toggleImage = (filename: string) => {
    setSelectedImages(prev => {
      const next = new Set(prev)
      if (next.has(filename)) next.delete(filename)
      else next.add(filename)
      return next
    })
  }

  const handleApprove = async () => {
    await approveMutation.mutateAsync({
      filenames: Array.from(selectedImages),
      renameMap: Object.fromEntries(
        Object.entries(renameMap).filter(([k]) => selectedImages.has(k))
      ),
    })
    setSelectedImages(new Set())
    setRenameMap({})
  }

  const handleDisapprove = async () => {
    await disapproveMutation.mutateAsync(Array.from(selectedImages))
    setSelectedImages(new Set())
  }

  const handleDownloadZip = async () => {
    const blob = await galleryApi.downloadZip(Array.from(selectedImages))
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'images.zip'
    a.click()
    URL.revokeObjectURL(url)
  }

  const totals = stats?.totals || { pending: 0, approved: 0, disapproved: 0 }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold">Gallery</h1>
          <div className="flex gap-3 text-sm">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-warning inline-block" />
              {totals.pending} pending
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-success inline-block" />
              {totals.approved} approved
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-destructive inline-block" />
              {totals.disapproved} disapproved
            </span>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-2" />Refresh
        </Button>
      </div>

      {/* Bulk Actions */}
      {selectedImages.size > 0 && (
        <div className="px-4 py-2 bg-muted border-b flex items-center gap-2">
          <Badge variant="secondary">{selectedImages.size} selected</Badge>
          {activeTab === 'pending' && (
            <>
              <Button size="sm" variant="success" onClick={handleApprove} isLoading={approveMutation.isPending}>
                <CheckCircle className="w-4 h-4 mr-2" />Approve
              </Button>
              <Button size="sm" variant="destructive" onClick={handleDisapprove} isLoading={disapproveMutation.isPending}>
                <XCircle className="w-4 h-4 mr-2" />Disapprove
              </Button>
            </>
          )}
          {activeTab === 'approved' && (
            <Button size="sm" variant="outline" onClick={() => undoMutation.mutate({ filenames: Array.from(selectedImages), fromStatus: 'approved' })}>
              <RotateCcw className="w-4 h-4 mr-2" />Undo
            </Button>
          )}
          {activeTab === 'disapproved' && (
            <Button size="sm" variant="outline" onClick={() => undoMutation.mutate({ filenames: Array.from(selectedImages), fromStatus: 'disapproved' })}>
              <RotateCcw className="w-4 h-4 mr-2" />Recover
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={handleDownloadZip}>
            <Download className="w-4 h-4 mr-2" />Download ZIP
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelectedImages(new Set())}>Clear</Button>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="flex-1 flex flex-col overflow-hidden">
        <TabsList className="mx-4 mt-4 w-fit">
          <TabsTrigger value="pending">
            Pending <Badge variant="outline" className="ml-2 text-xs">{totals.pending}</Badge>
          </TabsTrigger>
          <TabsTrigger value="approved">
            Approved <Badge variant="outline" className="ml-2 text-xs">{totals.approved}</Badge>
          </TabsTrigger>
          <TabsTrigger value="disapproved">
            Disapproved <Badge variant="outline" className="ml-2 text-xs">{totals.disapproved}</Badge>
          </TabsTrigger>
        </TabsList>

        {(['pending', 'approved', 'disapproved'] as GalleryStatus[]).map(status => (
          <TabsContent key={status} value={status} className="flex-1 overflow-auto px-4 pb-4">
            <ImageGrid
              images={gallery?.items || []}
              status={status}
              isLoading={isLoading}
              selectedImages={selectedImages}
              renameMap={renameMap}
              columns={columns}
              onColumnsChange={setColumns}
              onToggle={toggleImage}
              onRename={(filename, value) => setRenameMap(prev => ({ ...prev, [filename]: value }))}
              onSelectAll={() => setSelectedImages(new Set((gallery?.items || []).map(i => i.filename)))}
              onClearAll={() => setSelectedImages(new Set())}
              onAction={async (action, filename) => {
                if (action === 'approve') await approveMutation.mutateAsync({ filenames: [filename] })
                if (action === 'disapprove') await disapproveMutation.mutateAsync([filename])
                if (action === 'undo-approved') await undoMutation.mutateAsync({ filenames: [filename], fromStatus: 'approved' })
                if (action === 'undo-disapproved') await undoMutation.mutateAsync({ filenames: [filename], fromStatus: 'disapproved' })
              }}
            />
            {/* Pagination */}
            {gallery && gallery.pages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-4">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {page} of {gallery.pages} ({gallery.total} total)
                </span>
                <Button variant="outline" size="sm" disabled={page >= gallery.pages} onClick={() => setPage(p => p + 1)}>
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}

interface ImageGridProps {
  images: GalleryImage[]
  status: GalleryStatus
  isLoading: boolean
  selectedImages: Set<string>
  renameMap: Record<string, string>
  columns: number
  onColumnsChange: (n: number) => void
  onToggle: (filename: string) => void
  onRename: (filename: string, value: string) => void
  onSelectAll: () => void
  onClearAll: () => void
  onAction: (action: string, filename: string) => Promise<void>
}

const ImageGrid: React.FC<ImageGridProps> = ({
  images, status, isLoading, selectedImages, renameMap,
  columns, onColumnsChange,
  onToggle, onRename, onSelectAll, onClearAll, onAction
}) => {
  if (isLoading) return (
    <div className="flex items-center justify-center h-48">
      <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
    </div>
  )

  if (images.length === 0) return (
    <div className="text-center py-16 text-muted-foreground">
      <ImageIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
      <p>No {status} images</p>
    </div>
  )

  return (
    <>
      <div className="flex items-center gap-2 mb-4 mt-2 flex-wrap">
        <Button variant="outline" size="sm" onClick={onSelectAll}>Select All</Button>
        <Button variant="outline" size="sm" onClick={onClearAll}>Clear</Button>
        <span className="text-sm text-muted-foreground">{images.length} images</span>
        <div className="flex items-center gap-2 ml-auto">
          <LayoutGrid className="w-4 h-4 text-muted-foreground" />
          <span className="text-xs text-muted-foreground w-5 text-center">{columns}</span>
          <Slider
            min={2}
            max={8}
            step={1}
            value={[columns]}
            onValueChange={([v]) => onColumnsChange(v)}
            className="w-28"
          />
        </div>
      </div>
      <div className="gap-3" style={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        {images.map(img => (
          <ImageCard
            key={img.filename}
            image={img}
            status={status}
            isSelected={selectedImages.has(img.filename)}
            renameValue={renameMap[img.filename] || ''}
            onToggle={() => onToggle(img.filename)}
            onRename={(v) => onRename(img.filename, v)}
            onAction={(action) => onAction(action, img.filename)}
          />
        ))}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// ImageDetailModal
// ---------------------------------------------------------------------------

interface ImageDetailModalProps {
  image: GalleryImage
  status: GalleryStatus
  onClose: () => void
}

const ImageDetailModal: React.FC<ImageDetailModalProps> = ({ image, status, onClose }) => {
  const [metadata, setMetadata] = useState<ImageMetadata | null>(null)
  const [loading, setLoading] = useState(true)
  const refImageUrl = galleryApi.getRefImageUrl(image.filename, status)

  React.useEffect(() => {
    setLoading(true)
    galleryApi.getMetadata(image.filename, status)
      .then(setMetadata)
      .catch(() => setMetadata(null))
      .finally(() => setLoading(false))
  }, [image.filename, status])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-base font-semibold mb-4 pr-6 truncate">{image.filename}</h2>

        <div className="grid grid-cols-2 gap-4">
          {/* Generated image */}
          <div>
            <p className="text-xs text-muted-foreground mb-1">Generated</p>
            <img
              src={galleryApi.getThumbnailUrl(image.filename, status)}
              alt="generated"
              className="w-full rounded-lg object-cover"
            />
          </div>

          {/* Reference image */}
          <div>
            <p className="text-xs text-muted-foreground mb-1">Reference</p>
            <img
              src={refImageUrl}
              alt="reference"
              className="w-full rounded-lg object-cover"
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = 'none'
                const sibling = e.currentTarget.nextElementSibling as HTMLElement | null
                if (sibling) sibling.style.display = 'flex'
              }}
            />
            <div className="hidden items-center justify-center h-32 rounded-lg bg-muted text-xs text-muted-foreground">
              No reference image
            </div>
          </div>
        </div>

        {/* Metadata */}
        <div className="mt-4 space-y-3">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading metadata...
            </div>
          )}
          {!loading && metadata && (
            <>
              {metadata.persona && (
                <div>
                  <p className="text-xs text-muted-foreground mb-0.5">Persona</p>
                  <p className="text-sm">{metadata.persona}</p>
                </div>
              )}
              {metadata.seed != null && (
                <div>
                  <p className="text-xs text-muted-foreground mb-0.5">Seed</p>
                  <p className="text-sm font-mono">{metadata.seed}</p>
                </div>
              )}
              {metadata.prompt && (
                <div>
                  <p className="text-xs text-muted-foreground mb-0.5">Prompt</p>
                  <p className="text-sm whitespace-pre-wrap break-words">{metadata.prompt}</p>
                </div>
              )}
              {!metadata.persona && metadata.seed == null && !metadata.prompt && (
                <p className="text-sm text-muted-foreground">No metadata available</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ImageCard
// ---------------------------------------------------------------------------

interface ImageCardProps {
  image: GalleryImage
  status: GalleryStatus
  isSelected: boolean
  renameValue: string
  onToggle: () => void
  onRename: (value: string) => void
  onAction: (action: string) => Promise<void>
}

const ImageCard: React.FC<ImageCardProps> = ({
  image, status, isSelected, renameValue, onToggle, onRename, onAction
}) => {
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [showDetail, setShowDetail] = useState(false)
  const thumbnailUrl = galleryApi.getThumbnailUrl(image.filename, status)

  const handleAction = async (action: string) => {
    setActionLoading(action)
    try {
      await onAction(action)
    } finally {
      setActionLoading(null)
    }
  }

  // Use created_at to show relative time, with fallback
  const timeAgo = React.useMemo(() => {
    try {
      return formatDistanceToNow(new Date(image.created_at), { addSuffix: true })
    } catch {
      return ''
    }
  }, [image.created_at])

  return (
    <div className={`relative rounded-lg border-2 overflow-hidden group transition-all
      ${isSelected ? 'border-primary shadow-md' : 'border-transparent hover:border-muted-foreground/30'}`}
    >
      <div className="aspect-[9/16] bg-muted relative cursor-pointer" onClick={onToggle}>
        <img
          src={thumbnailUrl}
          alt={image.filename}
          className="w-full h-full object-cover"
          loading="lazy"
        />
        <div className="absolute top-2 left-2">
          <Checkbox
            checked={isSelected}
            onCheckedChange={() => onToggle()}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      </div>

      <div className="p-2 space-y-1.5">
        <p className="text-xs truncate text-muted-foreground" title={image.filename}>
          {image.filename}
        </p>
        {timeAgo && (
          <p className="text-xs text-muted-foreground/70">{timeAgo}</p>
        )}

        {/* Rename input for pending */}
        {status === 'pending' && (
          <Input
            placeholder="Rename..."
            value={renameValue}
            onChange={(e) => onRename(e.target.value)}
            className="h-6 text-xs"
            onClick={(e) => e.stopPropagation()}
          />
        )}

        {/* Action buttons */}
        <div className="flex gap-1">
          {status === 'pending' && (
            <>
              <Button
                size="sm"
                variant="success"
                className="flex-1 h-7 text-xs"
                onClick={(e) => { e.stopPropagation(); void handleAction('approve') }}
                isLoading={actionLoading === 'approve'}
              >
                <CheckCircle className="w-3 h-3 mr-1" />OK
              </Button>
              <Button
                size="sm"
                variant="destructive"
                className="flex-1 h-7 text-xs"
                onClick={(e) => { e.stopPropagation(); void handleAction('disapprove') }}
                isLoading={actionLoading === 'disapprove'}
              >
                <XCircle className="w-3 h-3 mr-1" />No
              </Button>
            </>
          )}
          {status === 'approved' && (
            <Button
              size="sm"
              variant="outline"
              className="flex-1 h-7 text-xs"
              onClick={(e) => { e.stopPropagation(); void handleAction('undo-approved') }}
              isLoading={actionLoading === 'undo-approved'}
            >
              <RotateCcw className="w-3 h-3 mr-1" />Undo
            </Button>
          )}
          {status === 'disapproved' && (
            <Button
              size="sm"
              variant="outline"
              className="flex-1 h-7 text-xs"
              onClick={(e) => { e.stopPropagation(); void handleAction('undo-disapproved') }}
              isLoading={actionLoading === 'undo-disapproved'}
            >
              <RotateCcw className="w-3 h-3 mr-1" />Recover
            </Button>
          )}
          <button
            className="flex items-center justify-center h-7 w-7 rounded-md border border-input hover:bg-accent transition-colors"
            onClick={(e) => { e.stopPropagation(); setShowDetail(true) }}
            title="View metadata"
          >
            <Info className="w-3 h-3" />
          </button>
          <a
            href={galleryApi.getDownloadUrl(image.filename)}
            download
            className="flex items-center justify-center h-7 w-7 rounded-md border border-input hover:bg-accent transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <Download className="w-3 h-3" />
          </a>
        </div>
      </div>

      {showDetail && (
        <ImageDetailModal
          image={image}
          status={status}
          onClose={() => setShowDetail(false)}
        />
      )}
    </div>
  )
}
