// The workspace image library grid: pagination, filtering, selection, upload
// and delete. Extracted verbatim from WorkspacePage.
import React, { useState } from 'react'
import { workspaceApi } from '@/api/workspace'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { format } from 'date-fns'
import { RefreshCw, CheckSquare, Square, Loader2, Image as ImageIcon, Trash2, CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import type { RefImage } from '@/types'

const PER_PAGE = 48

type FilterStatus = 'all' | 'unused' | 'used'
type SortBy = 'newest' | 'oldest' | 'name_asc' | 'name_desc'

export const ImageLibrary: React.FC<{
  images: RefImage[]
  selectedPaths: Set<string>
  onToggle: (path: string) => void
  onDelete: (filename: string) => void
  deletingFilename: string | null
  onSelectAll: (paths: string[]) => void
  onClearSelection: () => void
  onRefresh: () => void
}> = ({ images, selectedPaths, onToggle, onDelete, deletingFilename, onSelectAll, onClearSelection, onRefresh }) => {
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all')
  const [sortBy, setSortBy] = useState<SortBy>('newest')
  const [groupByDay, setGroupByDay] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)

  const filtered = React.useMemo(() => {
    if (filterStatus === 'unused') return images.filter(i => !i.is_used)
    if (filterStatus === 'used') return images.filter(i => i.is_used)
    return images
  }, [images, filterStatus])

  const sorted = React.useMemo(() => {
    return [...filtered].sort((a, b) => {
      if (sortBy === 'newest') return b.modified_at - a.modified_at
      if (sortBy === 'oldest') return a.modified_at - b.modified_at
      if (sortBy === 'name_asc') return a.filename.localeCompare(b.filename)
      return b.filename.localeCompare(a.filename)
    })
  }, [filtered, sortBy])

  const totalPages = Math.max(1, Math.ceil(sorted.length / PER_PAGE))
  const safePage = Math.min(currentPage, totalPages)
  const paginated = sorted.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE)

  React.useEffect(() => { setCurrentPage(1) }, [filterStatus, sortBy, images.length])

  const displayGroups = React.useMemo(() => {
    if (!groupByDay) return [{ label: null as string | null, items: paginated }]
    const groups: Record<string, RefImage[]> = {}
    for (const img of paginated) {
      const key = format(new Date(img.modified_at * 1000), 'yyyy-MM-dd')
      if (!groups[key]) groups[key] = []
      groups[key].push(img)
    }
    return Object.entries(groups).map(([key, items]) => ({
      label: format(new Date(key + 'T00:00:00'), 'EEEE, MMMM d, yyyy'),
      items,
    }))
  }, [paginated, groupByDay])

  const unusedCount = images.filter(i => !i.is_used).length
  const usedCount = images.filter(i => i.is_used).length

  if (images.length === 0) {
    return (
      <div className="text-center py-16 text-muted-foreground">
        <ImageIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No images yet</p>
        <p className="text-xs mt-1">Upload images above to get started</p>
      </div>
    )
  }

  const renderGrid = (items: RefImage[]) => (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
      {items.map(img => {
        const isSelected = selectedPaths.has(img.path)
        const isDeleting = deletingFilename === img.filename
        return (
          <div
            key={img.filename}
            className={`relative rounded-lg border-2 overflow-hidden transition-all
              ${isSelected
                ? 'border-amber-500 shadow-md'
                : img.is_used
                  ? 'border-yellow-500/70 hover:border-yellow-500'
                  : 'border-green-500/70 hover:border-green-500'}
              ${isDeleting ? 'opacity-40 pointer-events-none' : ''}`}
          >
            <div
              className="aspect-square bg-muted cursor-pointer"
              onClick={() => onToggle(img.path)}
            >
              <img
                src={workspaceApi.getRefImageThumbnailUrl(img.filename)}
                alt={img.filename}
                className="w-full h-full object-cover"
                loading="lazy"
              />
            </div>
            <div className="p-2 flex items-start justify-between gap-1">
              <div className="min-w-0 flex-1 cursor-pointer" onClick={() => onToggle(img.path)}>
                <p className="text-xs truncate font-medium">{img.filename}</p>
                {img.use_count > 0 && (
                  <p className="text-xs text-muted-foreground">{img.use_count}× used</p>
                )}
              </div>
              <button
                className="shrink-0 p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                onClick={(e) => { e.stopPropagation(); onDelete(img.filename) }}
                title="Delete"
              >
                {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              </button>
            </div>
            {isSelected && (
              <div className="absolute top-2 right-2 w-5 h-5 bg-amber-500 rounded-full flex items-center justify-center">
                <CheckSquare className="w-3 h-3 text-white" />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => onSelectAll(sorted.map(i => i.path))}>
          <CheckSquare className="w-4 h-4 mr-1.5" />Select All ({filtered.length})
        </Button>
        <Button variant="outline" size="sm" onClick={onClearSelection}>
          <Square className="w-4 h-4 mr-1.5" />Clear
        </Button>
        <Button variant="outline" size="sm" onClick={onRefresh}>
          <RefreshCw className="w-4 h-4 mr-1.5" />Refresh
        </Button>

        <div className="flex-1" />

        {/* Filter */}
        <Select value={filterStatus} onValueChange={(v) => setFilterStatus(v as FilterStatus)}>
          <SelectTrigger className="h-8 w-[120px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All ({images.length})</SelectItem>
            <SelectItem value="unused">Unused ({unusedCount})</SelectItem>
            <SelectItem value="used">Used ({usedCount})</SelectItem>
          </SelectContent>
        </Select>

        {/* Sort */}
        <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortBy)}>
          <SelectTrigger className="h-8 w-[130px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="newest">Newest first</SelectItem>
            <SelectItem value="oldest">Oldest first</SelectItem>
            <SelectItem value="name_asc">Name A→Z</SelectItem>
            <SelectItem value="name_desc">Name Z→A</SelectItem>
          </SelectContent>
        </Select>

        {/* Group by day toggle */}
        <button
          onClick={() => setGroupByDay(v => !v)}
          className={`flex items-center gap-1.5 h-8 px-2.5 rounded-md text-xs font-medium border transition-colors ${
            groupByDay
              ? 'bg-primary/10 border-primary/30 text-primary'
              : 'bg-background border-border text-muted-foreground hover:text-foreground'
          }`}
          title="Group by day"
        >
          <CalendarDays className="w-3.5 h-3.5" />
          By Day
        </button>
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <ImageIcon className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No images match the current filter</p>
        </div>
      ) : (
        <>
          {/* Summary */}
          <p className="text-xs text-muted-foreground">
            {filtered.length !== images.length
              ? `${filtered.length} of ${images.length} images`
              : `${images.length} images`}
            {totalPages > 1 && ` — page ${safePage} of ${totalPages}`}
          </p>

          {/* Image groups */}
          <div className="space-y-6">
            {displayGroups.map(({ label, items }) => (
              <div key={label ?? 'all'}>
                {label && (
                  <h3 className="text-xs font-medium text-muted-foreground mb-3 flex items-center gap-2">
                    <CalendarDays className="w-3.5 h-3.5" />
                    {label}
                    <span className="opacity-60">({items.length})</span>
                  </h3>
                )}
                {renderGrid(items)}
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2 pb-4">
              <Button
                variant="outline" size="sm"
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={safePage <= 1}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-xs text-muted-foreground min-w-[90px] text-center">
                Page {safePage} of {totalPages}
              </span>
              <Button
                variant="outline" size="sm"
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
