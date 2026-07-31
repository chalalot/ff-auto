// Config types
export interface PersonaSummary {
  name: string
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
  workflow_type?: string
  workflow_name?: string
  // Image Generation only: 't2i' | 'i2i' (see GENERATION_MODES in CreatePanel).
  generation_mode?: string
  enhance_prompt?: boolean
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

// The three workflow categories the Configuration sidebar offers.
export type WorkflowType = 'image_generation' | 'image_upscaler' | 'multiangle_edit'

/**
 * One entry in the Workflow Type / Mode vocabulary, configured in
 * Configure › Types rather than hardcoded here.
 *
 * `group` is the Type; kinds sharing a group become the Modes under it
 * (image_generation → I2I / T2I). The flags drive the sidebar: `needs_image`
 * decides whether Process can fire without a selected image, `uses_text`
 * whether a prompt box is shown, `uses_ai` whether the prompt agent can be
 * involved at all.
 */
export interface WorkflowKind {
  value: string
  label: string
  group: string
  group_label: string
  needs_image: boolean
  uses_text: boolean
  uses_ai: boolean
  hint: string
}

/** Which kinds a workflow file serves, and where its inputs are written. */
export interface WorkflowTagEntry {
  kinds: string[]
  /** Node id the prompt is written to; null lets the dispatcher detect it. */
  prompt_node?: string | null
  /** Node id the source image is written to; null means detect. */
  image_node?: string | null
  /** Free text on what the workflow is good for. Empty when never written. */
  note?: string
}

/** filename → entry. Untagged files are absent, not empty. */
export type WorkflowTagMap = Record<string, WorkflowTagEntry>

// ---------------------------------------------------------------------------
// Workflow file management (the /workflows page)
// ---------------------------------------------------------------------------

/** One node of a ComfyUI API-format graph. Array-valued inputs are wiring. */
export interface WorkflowGraphNode {
  class_type: string
  inputs: Record<string, unknown>
  _meta?: { title?: string }
}

/** A whole API-format workflow: node id → node. */
export type WorkflowGraph = Record<string, WorkflowGraphNode>

export interface WorkflowSummary {
  name: string
  node_count: number
  size_bytes: number
  modified_at: number
  /** False for files that fail to parse or aren't API format; `error` says why. */
  valid: boolean
  error?: string | null
}

export interface ProcessImageConfig {
  // Omitted for text-to-image, where `brief` is the only input.
  image_path?: string
  persona: string
  workflow_type: string
  vision_model: string
  variation_count: number
  // Text the prompt agent writes *from* rather than a finished prompt. With no
  // image_path this is the whole input (T2I with enhancement on).
  brief?: string
  // Which workflows/*.json graph to build from.
  workflow_name?: string
  // Per-run node-input overrides: { node_id: { input_key: value } }.
  // Seeds, LoRA, dimensions, CLIP type are all edited through these.
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
  run_id?: string | null
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
  metadata?: ImageMetadata
}

export interface ImageMetadata {
  seed?: number
  prompt?: string
  /** Workflow file that produced the image; absent on older results. */
  workflow?: string | null
  /** The operator's note about that workflow, editable from the detail view. */
  workflow_note?: string
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
