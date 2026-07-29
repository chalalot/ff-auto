import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/shared/Layout'

// Each page is its own lazy chunk so first paint only downloads the shell
// plus the page being visited. Pages use named exports, hence the .then maps.
const WorkspacePage = React.lazy(() => import('@/pages/WorkspacePage').then(m => ({ default: m.WorkspacePage })))
const GalleryPage = React.lazy(() => import('@/pages/GalleryPage').then(m => ({ default: m.GalleryPage })))
const MonitorPage = React.lazy(() => import('@/pages/MonitorPage').then(m => ({ default: m.MonitorPage })))
const PromptsPage = React.lazy(() => import('@/pages/PromptsPage').then(m => ({ default: m.PromptsPage })))
const WorkflowsPage = React.lazy(() => import('@/pages/WorkflowsPage').then(m => ({ default: m.WorkflowsPage })))
const VideoPage = React.lazy(() => import('@/pages/VideoPage').then(m => ({ default: m.VideoPage })))
const ArchivePage = React.lazy(() => import('@/pages/ArchivePage').then(m => ({ default: m.ArchivePage })))
const AnalysisPage = React.lazy(() => import('@/pages/AnalysisPage').then(m => ({ default: m.AnalysisPage })))
const ProjectsPage = React.lazy(() => import('@/pages/ProjectsPage').then(m => ({ default: m.ProjectsPage })))
const PipelineRunPage = React.lazy(() => import('@/pages/PipelineRunPage').then(m => ({ default: m.PipelineRunPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5000,
      throwOnError: false,
    },
  },
})

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, fontFamily: 'monospace', background: '#fff', color: '#c00' }}>
          <h2>Render error</h2>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>
            {this.state.error.message}
            {'\n\n'}
            {this.state.error.stack}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Navigate to="/workspace" replace />} />
              <Route path="workspace" element={<WorkspacePage />} />
              <Route path="gallery" element={<GalleryPage />} />
              <Route path="video" element={<VideoPage />} />
              <Route path="monitor" element={<MonitorPage />} />
              <Route path="prompts" element={<PromptsPage />} />
              <Route path="workflows" element={<WorkflowsPage />} />
              <Route path="archive" element={<ArchivePage />} />
              <Route path="analysis" element={<AnalysisPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="pipeline-runs/:runId" element={<PipelineRunPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}

export default App
