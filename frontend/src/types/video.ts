export interface KlingSettings {
  model_name: string        // "kling-v1.6" | "kling-v2.0" | "kling-v2.6"
  mode: string              // "std" | "pro"
  duration: string          // "5" | "10"
  aspect_ratio: string      // "16:9" | "9:16" | "1:1"
  cfg_scale: number
  negative_prompt?: string
  sound?: string            // "on" | "off"
  voice_list?: string[]
}

export interface KlingPreset {
  name: string
  settings: KlingSettings
}

export interface VideoGenerateRequest {
  image_path: string
  prompt?: string
  kling_settings: KlingSettings
  batch_id?: string
}

export interface VideoBatchItem {
  image_path: string
  prompt?: string
  variation_count: number
}

export interface VideoBatchRequest {
  items: VideoBatchItem[]
  kling_settings: KlingSettings
}

export interface VideoItem {
  id: number
  execution_id: string
  filename?: string
  source_image?: string
  prompt: string
  status: string
  created_at: string
  batch_id?: string
  video_url?: string
  thumbnail_url?: string
}

export interface VideoListResponse {
  items: VideoItem[]
  total: number
  page: number
  pages: number
}

export interface VideoStatusResponse {
  task_id: string
  status: string   // "pending" | "processing" | "succeed" | "failed"
  progress: number
  video_url?: string
  local_path?: string
  duration?: string
}

export interface VideoMergeRequest {
  filenames: string[]
  transition_type: string   // "Crossfade" | "Fade to Black" | "Simple Cut"
  transition_duration: number
}

export interface StoryboardVariation {
  variation: number
  concept_name: string
  prompt: string
}

export interface StoryboardResult {
  source_image: string
  persona: string
  variations: StoryboardVariation[]
}

export interface StoryboardResponse {
  results: StoryboardResult[]
}

export interface MusicAnalysisResponse {
  vibe: string
  lyrics: string
  analysis?: string
}
