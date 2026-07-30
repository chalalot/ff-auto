import type { ProcessImageConfig } from '@/types'

// The blank generation config. Shared by Flow › Create (which owns the config
// sidebar) and the LoRA page (whose caption pickers seed from the same shape) —
// two different surfaces, hence lib/ rather than either one's folder.
export const DEFAULT_CONFIG: Omit<ProcessImageConfig, 'image_path'> = {
  persona: '',
  workflow_type: 'image_generation',
  vision_model: 'gpt-4o',
  variation_count: 1,
  workflow_name: '',
}
