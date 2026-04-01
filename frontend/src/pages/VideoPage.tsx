import React, { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import { KlingSettingsPanel } from '@/components/video/KlingSettingsPanel'
import { KlingPresetManager } from '@/components/video/KlingPresetManager'
import { ImageSelector } from '@/components/video/ImageSelector'
import { SelectionQueue } from '@/components/video/SelectionQueue'
import { StoryboardGenerator } from '@/components/video/StoryboardGenerator'
import { BatchQueuePanel } from '@/components/video/BatchQueuePanel'
import { VideoGenerationHistory } from '@/components/video/VideoGenerationHistory'
import { VideoLibrary } from '@/components/video/VideoLibrary'
import { TimelineEditor } from '@/components/video/TimelineEditor'
import { MergeControls } from '@/components/video/MergeControls'
import { VideoGallery } from '@/components/video/VideoGallery'
import { AudioUploader } from '@/components/video/AudioUploader'
import { AudioTrimmer } from '@/components/video/AudioTrimmer'
import { MusicAnalysisResults } from '@/components/video/MusicAnalysisResults'
import { ComfyKlingSettingsPanel, DEFAULT_COMFY_KLING_SETTINGS } from '@/components/video/ComfyKlingSettingsPanel'
import type { KlingSettings, StoryboardResult, ComfyKlingSettings, VideoBackend } from '@/types/video'

const DEFAULT_KLING_SETTINGS: KlingSettings = {
  model_name: 'kling-v1.6',
  mode: 'std',
  duration: '5',
  aspect_ratio: '16:9',
  cfg_scale: 0.5,
}

interface QueueItem {
  image_path: string
  prompt?: string
  variation_count: number
}

export const VideoPage: React.FC = () => {
  // Create Video tab state
  const [selectedImages, setSelectedImages] = useState<string[]>([])
  const [queueItems, setQueueItems] = useState<QueueItem[]>([])
  const [klingSettings, setKlingSettings] = useState<KlingSettings>(DEFAULT_KLING_SETTINGS)
  const [storyboardResults, setStoryboardResults] = useState<StoryboardResult[]>([])
  const [videoBackend, setVideoBackend] = useState<VideoBackend>('api')
  const [comfySettings, setComfySettings] = useState<ComfyKlingSettings>(DEFAULT_COMFY_KLING_SETTINGS)

  // Video Constructor tab state
  const [timeline, setTimeline] = useState<string[]>([])

  // Song Producer tab state
  const [musicTaskId, setMusicTaskId] = useState<string | null>(null)
  const [audioFile, setAudioFile] = useState<File | null>(null)

  // ---- Image selector handlers ----
  const handleImageToggle = (path: string) => {
    setSelectedImages(prev => {
      if (prev.includes(path)) {
        setQueueItems(qi => qi.filter(q => q.image_path !== path))
        return prev.filter(p => p !== path)
      }
      setQueueItems(qi => [...qi, { image_path: path, prompt: '', variation_count: 1 }])
      return [...prev, path]
    })
  }

  // ---- Queue item handlers ----
  const handleQueueUpdate = (idx: number, update: Partial<{ prompt: string; variation_count: number }>) => {
    setQueueItems(prev => {
      const next = [...prev]
      next[idx] = { ...next[idx], ...update }
      return next
    })
  }

  const handleQueueRemove = (idx: number) => {
    setQueueItems(prev => {
      const removed = prev[idx]
      if (removed) {
        setSelectedImages(imgs => imgs.filter(p => p !== removed.image_path))
      }
      return prev.filter((_, i) => i !== idx)
    })
  }

  // ---- Storyboard handler ----
  const handlePromptsGenerated = (results: StoryboardResult[]) => {
    setStoryboardResults(results)
    // Merge generated prompts back into queue items (use first variation per image)
    setQueueItems(prev =>
      prev.map(item => {
        const match = results.find(r => r.source_image === item.image_path)
        if (!match || match.variations.length === 0) return item
        return { ...item, prompt: match.variations[0].prompt }
      })
    )
  }

  // ---- Timeline handlers ----
  const handleTimelineRemove = (filename: string) => {
    setTimeline(prev => prev.filter(f => f !== filename))
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b">
        <h1 className="text-xl font-bold">Video</h1>
      </div>

      <Tabs defaultValue="create" className="flex-1 flex flex-col overflow-hidden">
        <TabsList className="mx-4 mt-4 w-fit">
          <TabsTrigger value="create">Create Video</TabsTrigger>
          <TabsTrigger value="constructor">Video Constructor</TabsTrigger>
          <TabsTrigger value="gallery">Video Gallery</TabsTrigger>
          <TabsTrigger value="song">Song Producer</TabsTrigger>
        </TabsList>

        {/* ------------------------------------------------------------------ */}
        {/* Tab 1: Create Video                                                  */}
        {/* ------------------------------------------------------------------ */}
        <TabsContent value="create" className="flex-1 overflow-auto px-4 pb-6">
          <div className="max-w-4xl mx-auto space-y-6 pt-4">

            {/* Step 1: Select images */}
            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                1. Select Reference Images
              </h2>
              <ImageSelector selected={selectedImages} onToggle={handleImageToggle} />
            </section>

            <Separator />

            {/* Step 2: Queue */}
            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                2. Configure Queue ({queueItems.length} images)
              </h2>
              <SelectionQueue
                items={queueItems}
                onUpdate={handleQueueUpdate}
                onRemove={handleQueueRemove}
              />
            </section>

            {queueItems.length > 0 && (
              <>
                <Separator />

                {/* Step 3: Storyboard */}
                <section className="space-y-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    3. Generate Storyboard Prompts (optional)
                  </h2>
                  <StoryboardGenerator
                    imagePaths={selectedImages}
                    persona=""
                    onPromptsGenerated={handlePromptsGenerated}
                  />
                </section>

                <Separator />

                {/* Step 4: Kling settings */}
                <section className="space-y-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    4. Kling Settings
                  </h2>

                  {/* Backend selector */}
                  <div className="flex items-center gap-2 p-3 rounded-md border bg-muted/40">
                    <span className="text-sm font-medium mr-2">Backend:</span>
                    <button
                      onClick={() => setVideoBackend('api')}
                      className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                        videoBackend === 'api'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-background border hover:bg-accent'
                      }`}
                    >
                      Kling API
                    </button>
                    <button
                      onClick={() => setVideoBackend('comfy')}
                      className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                        videoBackend === 'comfy'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-background border hover:bg-accent'
                      }`}
                    >
                      ComfyUI (kling.json)
                    </button>
                    {videoBackend === 'comfy' && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        Uses KlingImage2VideoNode via Comfy Cloud
                      </span>
                    )}
                  </div>

                  {videoBackend === 'api' ? (
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                      <div className="lg:col-span-2">
                        <KlingSettingsPanel value={klingSettings} onChange={setKlingSettings} />
                      </div>
                      <div>
                        <KlingPresetManager
                          currentSettings={klingSettings}
                          onLoad={setKlingSettings}
                        />
                      </div>
                    </div>
                  ) : (
                    <ComfyKlingSettingsPanel value={comfySettings} onChange={setComfySettings} />
                  )}
                </section>

                <Separator />

                {/* Step 5: Queue to Kling */}
                <section className="space-y-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    5. Queue to Kling
                  </h2>
                  <BatchQueuePanel
                    items={queueItems}
                    klingSettings={klingSettings}
                    backend={videoBackend}
                    comfySettings={comfySettings}
                  />
                </section>
              </>
            )}

            <Separator />

            {/* Generation History */}
            <section className="space-y-3">
              <VideoGenerationHistory />
            </section>
          </div>
        </TabsContent>

        {/* ------------------------------------------------------------------ */}
        {/* Tab 2: Video Constructor                                             */}
        {/* ------------------------------------------------------------------ */}
        <TabsContent value="constructor" className="flex-1 overflow-auto px-4 pb-6">
          <div className="max-w-4xl mx-auto space-y-6 pt-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Video Library
                </h2>
                <VideoLibrary />
              </div>

              <div className="space-y-4">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Timeline
                </h2>
                <TimelineEditor
                  timeline={timeline}
                  onReorder={setTimeline}
                  onRemove={handleTimelineRemove}
                />

                {timeline.length > 0 && (
                  <>
                    <Separator />
                    <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                      Merge
                    </h2>
                    <MergeControls
                      filenames={timeline}
                      onMergeComplete={filename => {
                        setTimeline([])
                        // Optionally could open the merged video
                        console.log('Merged:', filename)
                      }}
                    />
                  </>
                )}
              </div>
            </div>
          </div>
        </TabsContent>

        {/* ------------------------------------------------------------------ */}
        {/* Tab 3: Video Gallery                                                 */}
        {/* ------------------------------------------------------------------ */}
        <TabsContent value="gallery" className="flex-1 overflow-auto px-4 pb-6">
          <div className="max-w-4xl mx-auto pt-4">
            <VideoGallery />
          </div>
        </TabsContent>

        {/* ------------------------------------------------------------------ */}
        {/* Tab 4: Song Producer                                                 */}
        {/* ------------------------------------------------------------------ */}
        <TabsContent value="song" className="flex-1 overflow-auto px-4 pb-6">
          <div className="max-w-2xl mx-auto space-y-6 pt-4">
            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Upload Audio
              </h2>
              <AudioUploader
                onFileSelected={setAudioFile}
                onUpload={setMusicTaskId}
              />
            </section>

            <Separator />

            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Trim Audio
              </h2>
              <AudioTrimmer file={audioFile} />
            </section>

            {musicTaskId && (
              <>
                <Separator />
                <section className="space-y-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    Analysis Results
                  </h2>
                  <MusicAnalysisResults taskId={musicTaskId} />
                </section>
              </>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
