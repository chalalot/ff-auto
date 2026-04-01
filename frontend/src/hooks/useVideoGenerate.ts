import { useMutation, useQueryClient } from '@tanstack/react-query'
import { videoApi } from '@/api/video'
import type { KlingSettings, VideoBatchItem, VideoBatchRequest } from '@/types/video'

export function useVideoGenerate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      image_path: string
      prompt?: string
      kling_settings: KlingSettings
    }) => videoApi.generate(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['videos'] }),
  })
}

export function useVideoBatchGenerate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: VideoBatchRequest) => videoApi.generateBatch(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['videos'] }),
  })
}
