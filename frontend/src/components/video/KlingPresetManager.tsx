import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2, Save, Trash2, Download } from 'lucide-react'
import { useKlingPresets } from '@/hooks/useVideoLibrary'
import type { KlingSettings } from '@/types/video'

interface KlingPresetManagerProps {
  currentSettings: KlingSettings
  onLoad: (settings: KlingSettings) => void
}

export const KlingPresetManager: React.FC<KlingPresetManagerProps> = ({
  currentSettings,
  onLoad,
}) => {
  const [presetName, setPresetName] = useState('')
  const { data: presets, isLoading, save, remove } = useKlingPresets()

  const handleSave = async () => {
    const name = presetName.trim()
    if (!name) return
    await save.mutateAsync({ name, settings: currentSettings })
    setPresetName('')
  }

  return (
    <div className="space-y-3">
      <Label className="text-xs text-muted-foreground uppercase tracking-wide">Presets</Label>

      {/* Save current as preset */}
      <div className="flex gap-2">
        <Input
          placeholder="Preset name..."
          value={presetName}
          onChange={e => setPresetName(e.target.value)}
          className="h-8 text-sm"
          onKeyDown={e => { if (e.key === 'Enter') void handleSave() }}
        />
        <Button
          size="sm"
          variant="outline"
          onClick={() => void handleSave()}
          disabled={!presetName.trim() || save.isPending}
        >
          {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        </Button>
      </div>

      {/* Preset list */}
      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading presets...
        </div>
      )}

      {presets && presets.length === 0 && (
        <p className="text-sm text-muted-foreground">No presets saved yet.</p>
      )}

      <div className="space-y-1.5">
        {(presets ?? []).map(preset => (
          <div
            key={preset.name}
            className="flex items-center justify-between rounded-md border px-3 py-1.5"
          >
            <span className="text-sm truncate">{preset.name}</span>
            <div className="flex gap-1 shrink-0">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0"
                onClick={() => onLoad(preset.settings)}
                title="Load preset"
              >
                <Download className="w-3.5 h-3.5" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                onClick={() => remove.mutate(preset.name)}
                disabled={remove.isPending}
                title="Delete preset"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
