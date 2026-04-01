import React from 'react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { KlingSettings } from '@/types/video'

interface KlingSettingsPanelProps {
  value: KlingSettings
  onChange: (s: KlingSettings) => void
}

export const KlingSettingsPanel: React.FC<KlingSettingsPanelProps> = ({ value, onChange }) => {
  const set = <K extends keyof KlingSettings>(key: K, val: KlingSettings[K]) =>
    onChange({ ...value, [key]: val })

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* Model */}
        <div className="space-y-1.5">
          <Label>Model</Label>
          <Select value={value.model_name} onValueChange={v => set('model_name', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="kling-v1.6">kling-v1.6</SelectItem>
              <SelectItem value="kling-v2.0">kling-v2.0</SelectItem>
              <SelectItem value="kling-v2.6">kling-v2.6</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Mode */}
        <div className="space-y-1.5">
          <Label>Mode</Label>
          <Select value={value.mode} onValueChange={v => set('mode', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="std">Standard</SelectItem>
              <SelectItem value="pro">Pro</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Duration */}
        <div className="space-y-1.5">
          <Label>Duration</Label>
          <Select value={value.duration} onValueChange={v => set('duration', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="5">5 seconds</SelectItem>
              <SelectItem value="10">10 seconds</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Aspect ratio */}
        <div className="space-y-1.5">
          <Label>Aspect Ratio</Label>
          <Select value={value.aspect_ratio} onValueChange={v => set('aspect_ratio', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="16:9">16:9 (Landscape)</SelectItem>
              <SelectItem value="9:16">9:16 (Portrait)</SelectItem>
              <SelectItem value="1:1">1:1 (Square)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* CFG Scale */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label>CFG Scale</Label>
          <span className="text-sm text-muted-foreground">{value.cfg_scale.toFixed(1)}</span>
        </div>
        <Slider
          min={0}
          max={1}
          step={0.1}
          value={[value.cfg_scale]}
          onValueChange={([v]) => set('cfg_scale', v)}
        />
      </div>

      {/* Negative prompt */}
      <div className="space-y-1.5">
        <Label>Negative Prompt</Label>
        <Input
          placeholder="What to avoid in the video..."
          value={value.negative_prompt ?? ''}
          onChange={e => set('negative_prompt', e.target.value)}
        />
      </div>

      {/* Sound — only for kling-v2.6 */}
      {value.model_name === 'kling-v2.6' && (
        <div className="space-y-1.5">
          <Label>Sound</Label>
          <Select value={value.sound ?? 'off'} onValueChange={v => set('sound', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="on">On</SelectItem>
              <SelectItem value="off">Off</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  )
}
