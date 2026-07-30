// Who actually generates the thing. Mirrors Provider in backend/models/review.py.
//
// Image and video work share one `generation_requests` queue, so every surface
// that reads that queue has to say which providers it means. Flow is the image
// conveyor; Video is its own surface because a video is an intermediate chain of
// ComfyUI workflows rather than one workflow end to end. Without scoping, Flow's
// rail counts video rows as image work and the Video page has no queue at all.
export type ReviewProvider = 'comfy_image' | 'comfy_video' | 'kling'

export const PROVIDER_LABEL: Record<string, string> = {
  comfy_image: 'ComfyUI image',
  comfy_video: 'ComfyUI video',
  kling: 'Kling API',
}

export const IMAGE_PROVIDERS: readonly ReviewProvider[] = ['comfy_image']
export const VIDEO_PROVIDERS: readonly ReviewProvider[] = ['comfy_video', 'kling']
