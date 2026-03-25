import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { galleryApi, type GalleryStatus } from '@/api/gallery'

export const useGalleryImages = (status: GalleryStatus, page: number = 1, perPage: number = 20) => {
  return useQuery({
    queryKey: ['gallery', status, page, perPage],
    queryFn: () => galleryApi.getImages({ status, page, per_page: perPage }),
  })
}

export const useGalleryStats = () => {
  return useQuery({
    queryKey: ['gallery', 'stats'],
    queryFn: galleryApi.getStats,
    staleTime: 30000,
  })
}

export const useApproveImages = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ filenames, renameMap }: { filenames: string[]; renameMap?: Record<string, string> }) =>
      galleryApi.approve(filenames, renameMap),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gallery'] })
    },
  })
}

export const useDisapproveImages = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (filenames: string[]) => galleryApi.disapprove(filenames),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gallery'] })
    },
  })
}

export const useUndoImages = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ filenames, fromStatus }: { filenames: string[]; fromStatus: 'approved' | 'disapproved' }) =>
      galleryApi.undo(filenames, fromStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gallery'] })
    },
  })
}
