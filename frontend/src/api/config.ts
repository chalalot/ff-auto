import { apiClient } from '@/lib/api-client'
import type { PersonaSummary, PersonaConfig, PresetConfig, LastUsedConfig } from '@/types'

export interface SelectOption {
  label: string
  value: string
}

export const configApi = {
  getPersonas: () =>
    apiClient.get<PersonaSummary[]>('/config/personas').then(r => r.data),

  getPersona: (name: string) =>
    apiClient.get<PersonaConfig>(`/config/personas/${name}`).then(r => r.data),

  updatePersona: (name: string, data: Partial<PersonaConfig>) =>
    apiClient.put(`/config/personas/${name}`, data).then(r => r.data),

  getPersonaTypes: () =>
    apiClient.get<string[]>('/config/persona-types').then(r => r.data),

  getPresets: () =>
    apiClient.get<PresetConfig[]>('/config/presets').then(r => r.data),

  getPreset: (name: string) =>
    apiClient.get<PresetConfig>(`/config/presets/${name}`).then(r => r.data),

  savePreset: (name: string, config: unknown) =>
    apiClient.post(`/config/presets/${name}`, { name, config }).then(r => r.data),

  deletePreset: (name: string) =>
    apiClient.delete(`/config/presets/${name}`).then(r => r.data),

  getLastUsed: () =>
    apiClient.get<LastUsedConfig>('/config/presets/_last_used').then(r => r.data),

  saveLastUsed: (config: LastUsedConfig) =>
    apiClient.put('/config/presets/_last_used', config).then(r => r.data),

  getWorkflowTypes: () =>
    apiClient.get<string[]>('/config/workflow-types').then(r => r.data),

  getVisionModels: () =>
    apiClient.get<SelectOption[]>('/config/vision-models').then(r => r.data),

  getClipModelTypes: () =>
    apiClient.get<string[]>('/config/clip-model-types').then(r => r.data),

  getLoraOptions: () =>
    apiClient.get<string[]>('/config/lora-options').then(r => r.data),
}
