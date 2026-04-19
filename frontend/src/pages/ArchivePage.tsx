import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Slider } from '@/components/ui/slider'
import { archiveApi } from '@/api/archive'
import { formatDistanceToNow } from 'date-fns'
import {
  RefreshCw,
  Image as ImageIcon,
  Loader2,
  ChevronLeft,
  ChevronRight,
  LayoutGrid,
  Info,
  X,
  Download,
  Archive,
} from 'lucide-react'
import type { ArchiveImage, ImageMetadata } from '@/types'

const ITEMS_PER_PAGE = 20

// Server names can be long slugs; this makes them friendlier in the UI
function serverLabel(name: string): string {
  return name.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// ------------------------------------------------------------------
// Hooks
// ------------------------------------------------------------------

function useArchiveImages(server: string | null, page: number) {
  return useQuery({
    queryKey: ['archive', 'list', server, page],
    queryFn: () =>
      archiveApi.list({
        server: server ?? undefined,
        page,
        per_page: ITEMS_PER_PAGE,
      }),
  })
}

// ------------------------------------------------------------------
// ArchivePage
// ------------------------------------------------------------------

export const ArchivePage: React.FC = () => {
  const [activeServer, setActiveServer] = useState<string | null>(null) // null = "All"
  const [page, setPage] = useState(1)
  const [columns, setColumns] = useState(4)

  const { data, isLoading, refetch } = useArchiveImages(activeServer, page)

  const servers = data?.servers ?? []

  const handleServerChange = (server: string | null) => {
    setActiveServer(server)
    setPage(1)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Archive className="w-5 h-5 text-muted-foreground" />
          <h1 className="text-xl font-bold">Archive</h1>
          {data && (
            <Badge variant="secondary" className="text-xs">
              {data.total} images
            </Badge>
          )}
          <span className="text-xs text-muted-foreground">read-only</span>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Server filter tabs */}
      {servers.length > 0 && (
        <div className="px-4 pt-3 pb-1 flex items-center gap-2 flex-wrap border-b">
          <button
            onClick={() => handleServerChange(null)}
            className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
              activeServer === null
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-accent'
            }`}
          >
            All
          </button>
          {servers.map((srv) => (
            <button
              key={srv}
              onClick={() => handleServerChange(srv)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                activeServer === srv
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-accent'
              }`}
            >
              {serverLabel(srv)}
            </button>
          ))}
        </div>
      )}

      {/* Grid */}
      <div className="flex-1 overflow-auto px-4 pb-4">
        <ArchiveGrid
          images={data?.items ?? []}
          isLoading={isLoading}
          columns={columns}
          onColumnsChange={setColumns}
        />

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-4">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {data.pages} ({data.total} total)
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= data.pages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// ArchiveGrid
// ------------------------------------------------------------------

interface ArchiveGridProps {
  images: ArchiveImage[]
  isLoading: boolean
  columns: number
  onColumnsChange: (n: number) => void
}

const ArchiveGrid: React.FC<ArchiveGridProps> = ({
  images,
  isLoading,
  columns,
  onColumnsChange,
}) => {
  if (isLoading)
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    )

  if (images.length === 0)
    return (
      <div className="text-center py-16 text-muted-foreground">
        <ImageIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No archived images found</p>
      </div>
    )

  return (
    <>
      <div className="flex items-center gap-2 mb-4 mt-3 flex-wrap">
        <span className="text-sm text-muted-foreground">{images.length} shown</span>
        <div className="flex items-center gap-2 ml-auto">
          <LayoutGrid className="w-4 h-4 text-muted-foreground" />
          <span className="text-xs text-muted-foreground w-5 text-center">
            {columns}
          </span>
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
      <div
        className="gap-3"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        }}
      >
        {images.map((img) => (
          <ArchiveCard key={`${img.server}/${img.filename}`} image={img} />
        ))}
      </div>
    </>
  )
}

// ------------------------------------------------------------------
// ArchiveCard
// ------------------------------------------------------------------

interface ArchiveCardProps {
  image: ArchiveImage
}

const ArchiveCard: React.FC<ArchiveCardProps> = ({ image }) => {
  const [showDetail, setShowDetail] = useState(false)
  const thumbnailUrl = archiveApi.getThumbnailUrl(image.server, image.filename)

  const timeAgo = React.useMemo(() => {
    try {
      return formatDistanceToNow(new Date(image.created_at * 1000), {
        addSuffix: true,
      })
    } catch {
      return ''
    }
  }, [image.created_at])

  return (
    <div className="relative rounded-lg border-2 border-transparent hover:border-muted-foreground/30 overflow-hidden group transition-all">
      {/* Thumbnail */}
      <div className="aspect-[9/16] bg-muted relative">
        <img
          src={thumbnailUrl}
          alt={image.filename}
          className="w-full h-full object-cover"
          loading="lazy"
        />
        {/* Server badge */}
        <div className="absolute top-2 right-2">
          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-black/60 text-white">
            {serverLabel(image.server)}
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="p-2 space-y-1.5">
        <p
          className="text-xs truncate text-muted-foreground"
          title={image.filename}
        >
          {image.filename}
        </p>
        {timeAgo && (
          <p className="text-xs text-muted-foreground/70">{timeAgo}</p>
        )}

        {/* Actions */}
        <div className="flex gap-1">
          <button
            className="flex items-center justify-center h-7 w-7 rounded-md border border-input hover:bg-accent transition-colors"
            onClick={() => setShowDetail(true)}
            title="View metadata"
          >
            <Info className="w-3 h-3" />
          </button>
          <a
            href={archiveApi.getImageUrl(image.server, image.filename)}
            download
            className="flex items-center justify-center h-7 w-7 rounded-md border border-input hover:bg-accent transition-colors"
            title="Download"
          >
            <Download className="w-3 h-3" />
          </a>
        </div>
      </div>

      {showDetail && (
        <ArchiveDetailModal image={image} onClose={() => setShowDetail(false)} />
      )}
    </div>
  )
}

// ------------------------------------------------------------------
// ArchiveDetailModal
// ------------------------------------------------------------------

interface ArchiveDetailModalProps {
  image: ArchiveImage
  onClose: () => void
}

const ArchiveDetailModal: React.FC<ArchiveDetailModalProps> = ({
  image,
  onClose,
}) => {
  const [metadata, setMetadata] = useState<ImageMetadata | null>(null)
  const [loading, setLoading] = useState(true)

  const refImageUrl = archiveApi.getRefImageUrl(image.server, image.filename)
  const fullImageUrl = archiveApi.getThumbnailUrl(image.server, image.filename)

  React.useEffect(() => {
    setLoading(true)
    archiveApi
      .getMetadata(image.server, image.filename)
      .then(setMetadata)
      .catch(() => setMetadata(null))
      .finally(() => setLoading(false))
  }, [image.server, image.filename])

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

        <div className="mb-1 flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {serverLabel(image.server)}
          </Badge>
        </div>
        <h2 className="text-base font-semibold mb-4 pr-6 truncate">
          {image.filename}
        </h2>

        {/* Images side-by-side */}
        <div className="grid grid-cols-2 gap-4">
          {/* Generated result */}
          <div>
            <p className="text-xs text-muted-foreground mb-1">Generated</p>
            <img
              src={fullImageUrl}
              alt="generated"
              className="w-full rounded-lg object-cover"
            />
          </div>

          {/* Reference image from processed/ */}
          <div>
            <p className="text-xs text-muted-foreground mb-1">Reference</p>
            <img
              src={refImageUrl}
              alt="reference"
              className="w-full rounded-lg object-cover"
              onError={(e) => {
                ;(e.currentTarget as HTMLImageElement).style.display = 'none'
                const sibling = e.currentTarget
                  .nextElementSibling as HTMLElement | null
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
                  <p className="text-sm whitespace-pre-wrap break-words">
                    {metadata.prompt}
                  </p>
                </div>
              )}
              {!metadata.persona && metadata.seed == null && !metadata.prompt && (
                <p className="text-sm text-muted-foreground">
                  No metadata available
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
