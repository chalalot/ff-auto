import { useMutation } from '@tanstack/react-query'
import { videoApi } from '@/api/video'
import type { StoryboardResponse } from '@/types/video'

const POLL_INTERVAL_MS = 3000

export function useStoryboard() {
  return useMutation({
    mutationFn: async (body: {
      image_paths: string[]
      vision_model?: string
      persona?: string
      variation_count?: number
    }): Promise<StoryboardResponse> => {
      const { task_id } = await videoApi.dispatchStoryboard(body)

      while (true) {
        await new Promise(r => setTimeout(r, POLL_INTERVAL_MS))
        const status = await videoApi.getStoryboardStatus(task_id)
        if (status.state === 'SUCCESS' && status.result) return status.result
        if (status.state === 'FAILURE') throw new Error(status.error ?? 'Storyboard generation failed')
      }
    },
  })
}
