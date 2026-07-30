import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/shared/Layout'

// Each page is its own lazy chunk so first paint only downloads the shell
// plus the page being visited. Pages use named exports, hence the .then maps.
const FlowPage = React.lazy(() => import('@/pages/FlowPage').then(m => ({ default: m.FlowPage })))
const LibraryPage = React.lazy(() => import('@/pages/LibraryPage').then(m => ({ default: m.LibraryPage })))
const LoraPage = React.lazy(() => import('@/pages/LoraPage').then(m => ({ default: m.LoraPage })))
const ConfigurePage = React.lazy(() => import('@/pages/ConfigurePage').then(m => ({ default: m.ConfigurePage })))
const MonitorPage = React.lazy(() => import('@/pages/MonitorPage').then(m => ({ default: m.MonitorPage })))
const VideoPage = React.lazy(() => import('@/pages/VideoPage').then(m => ({ default: m.VideoPage })))
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
              <Route index element={<Navigate to="/flow" replace />} />
              <Route path="flow" element={<FlowPage />} />
              <Route path="library" element={<LibraryPage />} />
              <Route path="lora" element={<LoraPage />} />
              <Route path="configure" element={<ConfigurePage />} />
              <Route path="video" element={<VideoPage />} />
              <Route path="monitor" element={<MonitorPage />} />
              <Route path="analysis" element={<AnalysisPage />} />
              {/* The eight pre-Flow routes still exist in bookmarks, other
                  users' tabs and old toasts — send each to where its content
                  lives now instead of 404ing. */}
              <Route path="workspace" element={<Navigate to="/flow" replace />} />
              <Route path="gallery" element={<Navigate to="/flow?stage=images" replace />} />
              <Route path="archive" element={<Navigate to="/library" replace />} />
              <Route path="prompts" element={<Navigate to="/configure" replace />} />
              <Route path="workflows" element={<Navigate to="/configure" replace />} />
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
