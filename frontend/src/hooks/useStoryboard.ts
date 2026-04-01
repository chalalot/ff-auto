import { useMutation } from '@tanstack/react-query'
import { videoApi } from '@/api/video'

export function useStoryboard() {
  return useMutation({
    mutationFn: (body: {
      image_paths: string[]
      vision_model?: string
      persona?: string
      variation_count?: number
    }) => videoApi.generateStoryboard(body),
  })
}
