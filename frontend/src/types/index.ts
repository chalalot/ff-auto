// Config types
export interface PersonaSummary {
  name: string
  type: string
  hair_color: string
  hairstyles: string[]
  lora_name: string
}

export interface PersonaConfig extends PersonaSummary {
  lora_name: string
}

export interface PresetConfig {
  name: string
  config: ProcessImageConfig
}

export interface LastUsedConfig {
  persona?: string
  vision_model?: string
  batch_limit?: number
  variations?: number
  lora_name?: string
  seed_strategy?: string
  base_seed?: number
  workflow_type?: string
}

// Workspace types
export interface RefImage {
  filename: string
  path: string
  size_bytes: number
  modified_at: number
  thumbnail_url: string
  use_count: number
  is_used: boolean
}

export interface InputImage {
  filename: string
  path: string
  size_bytes: number
  modified_at: string
  thumbnail_url: string
}

export interface PipelineInfo {
  pipeline_type: string
  media_type: string   // "image" | "video"
  label: string
  available: boolean
}

export interface WorkflowParamInput {
  key: string
  value: unknown
  type: 'integer' | 'number' | 'boolean' | 'string'
  locked: boolean
  locked_reason?: string | null
}

export interface WorkflowParamNode {
  node_id: string
  class_type: string
  title: string
  inputs: WorkflowParamInput[]
}

export interface WorkflowParameters {
  workflow?: string
  pipeline_type?: string
  nodes: WorkflowParamNode[]
}

export interface ProcessImageConfig {
  image_path: string
  persona: string
  workflow_type: string
  vision_model: string
  variation_count: number
  seed_strategy: string
  base_seed: number
  lora_name: string
  // Which workflows/*.json graph to build from (backend defaults to workflow.json).
  workflow_name?: string
  // Per-run node-input overrides: { node_id: { input_key: value } }.
  workflow_overrides?: Record<string, Record<string, unknown>>
}

export interface TaskStatusResponse {
  task_id: string
  state: 'PENDING' | 'STARTED' | 'PROGRESS' | 'SUCCESS' | 'FAILURE' | 'RETRY'
  status_message: string
  progress: number
  result?: unknown
  error?: string
}

export interface CaptionExportEntry {
  stem: string          // original filename stem, e.g. "image_1"
  path: string          // absolute path in PROCESSED_DIR
  original_ext: string  // e.g. ".jpg"
}

export interface ExecutionRecord {
  id: number
  execution_id: string
  prompt?: string
  persona?: string
  image_ref_path?: string
  result_image_path?: string
  status: string
  created_at: string
}

export interface ActiveTask {
  task_id: string
  state: string
  status_message: string
  progress: number
  image_path?: string
  persona: string
  dispatched_at?: number
  task_type: string        // "image_process" | "caption_export"
  image_count?: number
}

// Gallery types
export interface GalleryImage {
  filename: string
  path: string
  thumbnail_url: string
  created_at: string
  persona?: string
  metadata?: ImageMetadata
}

export interface ImageMetadata {
  seed?: number
  prompt?: string
  workflow?: string
  persona?: string
  ref_image?: string
}

export interface GalleryResponse {
  items: GalleryImage[]
  total: number
  page: number
  pages: number
}

export interface GalleryStats {
  daily: Array<{
    date: string
    pending: number
    approved: number
    disapproved: number
  }>
  totals: {
    pending: number
    approved: number
    disapproved: number
  }
}

// Archive types
export interface ArchiveImage {
  server: string
  filename: string
  thumbnail_url: string
  created_at: number
  date: string
}

export interface ArchiveListResponse {
  servers: string[]
  items: ArchiveImage[]
  total: number
  page: number
  pages: number
  per_page: number
}

// Monitor types
export interface SystemHealth {
  cpu_percent: number
  ram: { total: number; used: number; percent: number }
  disk: { total: number; used: number; percent: number }
}
