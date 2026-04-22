import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2, Wand2, ChevronDown, ChevronUp } from 'lucide-react'
import { useStoryboard } from '@/hooks/useStoryboard'
import type { StoryboardResult } from '@/types/video'

const VISION_MODELS = [
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
]

interface StoryboardGeneratorProps {
  imagePaths: string[]
  persona: string
  onPromptsGenerated: (results: StoryboardResult[]) => void
}

export const StoryboardGenerator: React.FC<StoryboardGeneratorProps> = ({
  imagePaths,
  persona,
  onPromptsGenerated,
}) => {
  const [visionModel, setVisionModel] = useState('gpt-4o')
  const [variationCount, setVariationCount] = useState(1)
  const [localResults, setLocalResults] = useState<StoryboardResult[]>([])
  const [editedPrompts, setEditedPrompts] = useState<Record<string, Record<number, string>>>({})
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const mutation = useStoryboard()

  const handleGenerate = async () => {
    if (imagePaths.length === 0) return
    const res = await mutation.mutateAsync({
      image_paths: imagePaths,
      vision_model: visionModel,
      persona: persona || undefined,
      variation_count: variationCount,
    })
    setLocalResults(res.results)
    setEditedPrompts({})
  }

  const setPrompt = (source: string, varIdx: number, value: string) => {
    setEditedPrompts(prev => ({
      ...prev,
      [source]: { ...(prev[source] ?? {}), [varIdx]: value },
    }))
  }

  const handleUsePrompts = () => {
    const merged = localResults.map(r => ({
      ...r,
      variations: r.variations.map(v => ({
        ...v,
        prompt: editedPrompts[r.source_image]?.[v.variation] ?? v.prompt,
      })),
    }))
    onPromptsGenerated(merged)
  }

  const toggleExpanded = (source: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(source)) next.delete(source)
      else next.add(source)
      return next
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3 flex-wrap">
        <div className="space-y-1.5">
          <Label>Vision Model</Label>
          <Select value={visionModel} onValueChange={setVisionModel}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {VISION_MODELS.map(m => (
                <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label>Variations per image</Label>
          <Select
            value={String(variationCount)}
            onValueChange={v => setVariationCount(Number(v))}
          >
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[1, 2, 3, 4, 5].map(n => (
                <SelectItem key={n} value={String(n)}>{n}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          onClick={() => void handleGenerate()}
          disabled={imagePaths.length === 0 || mutation.isPending}
        >
          {mutation.isPending
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Generating...</>
            : <><Wand2 className="w-4 h-4 mr-2" />Generate Prompts</>
          }
        </Button>
      </div>

      {imagePaths.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Select images first, then generate storyboard prompts.
        </p>
      )}

      {mutation.isError && (
        <p className="text-sm text-destructive">Failed to generate prompts. Please try again.</p>
      )}

      {localResults.length > 0 && (
        <div className="space-y-3">
          {localResults.map(result => {
            const filename = result.source_image.split('/').pop() ?? result.source_image
            const isOpen = expanded.has(result.source_image)
            return (
              <div key={result.source_image} className="rounded-lg border overflow-hidden">
                <button
                  className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/50 transition-colors"
                  onClick={() => toggleExpanded(result.source_image)}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate max-w-xs">{filename}</span>
                    <Badge variant="outline" className="text-xs">{result.variations.length} variations</Badge>
                  </div>
                  {isOpen
                    ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
                    : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                </button>

                {isOpen && (
                  <div className="px-4 pb-4 space-y-3 border-t">
                    {result.variations.map(v => (
                      <div key={v.variation} className="space-y-1 pt-3">
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className="text-xs">#{v.variation}</Badge>
                          <span className="text-xs text-muted-foreground">{v.concept_name}</span>
                        </div>
                        <Textarea
                          value={editedPrompts[result.source_image]?.[v.variation] ?? v.prompt}
                          onChange={e => setPrompt(result.source_image, v.variation, e.target.value)}
                          className="text-sm min-h-[80px] resize-none"
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}

          <Button onClick={handleUsePrompts} className="w-full">
            Use These Prompts
          </Button>
        </div>
      )}
    </div>
  )
}
