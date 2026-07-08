import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ArrowLeft } from 'lucide-react'
import { projectsApi } from '@/api/projects'
import { GalleryPage } from '@/pages/GalleryPage'
import { ReviewQueuePage } from '@/pages/ReviewQueuePage'
import { AnalysisPage } from '@/pages/AnalysisPage'
import { AssetsPanel } from '@/components/workspace/AssetsPanel'

type Tab = 'gallery' | 'review' | 'analysis' | 'assets'

export const ProjectWorkspacePage: React.FC = () => {
  const { projectId = '' } = useParams()
  const [tab, setTab] = useState<Tab>('gallery')
  const { data: projects = [] } = useQuery({
    queryKey: ['projects', 'all'],
    queryFn: () => projectsApi.list(true),
  })
  const project = projects.find(p => p.id === projectId)

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center gap-4">
        <Link to="/projects" className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <h1 className="text-xl font-bold truncate">{project?.name ?? 'Project'}</h1>
        <Tabs value={tab} onValueChange={v => setTab(v as Tab)} className="ml-auto">
          <TabsList>
            <TabsTrigger value="gallery">Gallery</TabsTrigger>
            <TabsTrigger value="review">Review</TabsTrigger>
            <TabsTrigger value="analysis">Analysis</TabsTrigger>
            <TabsTrigger value="assets">Assets</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {tab === 'gallery' && <GalleryPage projectId={projectId} />}
        {tab === 'review' && <ReviewQueuePage projectId={projectId} />}
        {tab === 'analysis' && <AnalysisPage projectId={projectId} />}
        {tab === 'assets' && <AssetsPanel projectId={projectId} />}
      </div>
    </div>
  )
}
