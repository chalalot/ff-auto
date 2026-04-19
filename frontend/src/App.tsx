import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/shared/Layout'
import { WorkspacePage } from '@/pages/WorkspacePage'
import { GalleryPage } from '@/pages/GalleryPage'
import { MonitorPage } from '@/pages/MonitorPage'
import { PromptsPage } from '@/pages/PromptsPage'
import { VideoPage } from '@/pages/VideoPage'
import { ArchivePage } from '@/pages/ArchivePage'

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
              <Route path="archive" element={<ArchivePage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}

export default App
