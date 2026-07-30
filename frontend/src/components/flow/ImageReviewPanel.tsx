import React from 'react'
import { GalleryBrowser } from '@/components/gallery/GalleryBrowser'
import { toast } from '@/hooks/useToast'

// Judging generated images — the old Gallery › Pending tab, in the stage where
// it belongs. This is the last stage of the conveyor: approving ends the image's
// trip. The toast points at LoRA because that's what consumes approved images,
// not because training is a step every image takes.
export const ImageReviewPanel: React.FC = () => (
  <GalleryBrowser
    status="pending"
    onAfterAction={(action, filenames) => {
      if (action !== 'approve') return
      const n = filenames.length
      toast({
        title: `Approved ${n} ${n === 1 ? 'image' : 'images'}`,
        description: 'In the Library, and available as LoRA training data.',
        action: { label: 'Train a LoRA', to: '/lora' },
      })
    }}
  />
)
