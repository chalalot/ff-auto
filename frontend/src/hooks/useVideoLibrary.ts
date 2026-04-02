import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { videoApi } from '@/api/video'
import type { KlingPreset } from '@/types/video'

export function useVideoList(page = 1, perPage = 20) {
  return useQuery({
    queryKey: ['videos', page, perPage],
    queryFn: () => videoApi.listVideos({ page, per_page: perPage }),
    refetchInterval: (query) => {
      const items = query.state.data?.items || []
      const hasPending = items.some((item) => 
        ['pending', 'processing', 'submitted'].includes(item.status)
      )
      return hasPending ? 5000 : false
    },
  })
}

export function useKlingPresets() {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ['klingPresets'],
    queryFn: videoApi.getKlingPresets,
  })
  const save = useMutation({
    mutationFn: (preset: KlingPreset) => videoApi.saveKlingPreset(preset),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['klingPresets'] }),
  })
  const remove = useMutation({
    mutationFn: (name: string) => videoApi.deleteKlingPreset(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['klingPresets'] }),
  })
  return { ...query, save, remove }
}
