import React, { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PromptsPage } from '@/pages/PromptsPage'
import { WorkflowsPage } from '@/pages/WorkflowsPage'
import { WorkflowKindsPanel } from '@/components/workspace/WorkflowKindsPanel'

// The things you set up once and rarely touch: what the agents are told, which
// ComfyUI graphs are available and what each one is for, and the vocabulary of
// workflow types those tags come from. Grouped so the sidebar stops carrying an
// entry per settings page.
export const ConfigurePage: React.FC = () => {
  const [tab, setTab] = useState('prompts')

  return (
    <div className="flex h-full flex-col">
      <Tabs value={tab} onValueChange={setTab} className="flex flex-1 flex-col overflow-hidden">
        <TabsList className="mx-4 mt-4 w-fit">
          <TabsTrigger value="prompts">Prompts</TabsTrigger>
          <TabsTrigger value="workflows">Workflows</TabsTrigger>
          <TabsTrigger value="types">Types</TabsTrigger>
        </TabsList>
        <TabsContent value="prompts" className="flex-1 overflow-hidden">
          <PromptsPage />
        </TabsContent>
        <TabsContent value="workflows" className="flex-1 overflow-hidden">
          <WorkflowsPage />
        </TabsContent>
        <TabsContent value="types" className="flex-1 overflow-hidden">
          <WorkflowKindsPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}
