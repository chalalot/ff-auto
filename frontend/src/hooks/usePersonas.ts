import { useQuery } from '@tanstack/react-query'
import { configApi, type SelectOption } from '@/api/config'

export type { SelectOption }

export const usePersonas = () => {
  return useQuery({
    queryKey: ['config', 'personas'],
    queryFn: configApi.getPersonas,
    staleTime: 1000 * 60 * 60,
  })
}

export const useLastUsed = () => {
  return useQuery({
    queryKey: ['config', 'last-used'],
    queryFn: configApi.getLastUsed,
  })
}

export const useVisionModels = () => {
  return useQuery({
    queryKey: ['config', 'vision-models'],
    queryFn: configApi.getVisionModels,
    staleTime: Infinity,
  })
}

export const useClipModels = () => {
  return useQuery({
    queryKey: ['config', 'clip-models'],
    queryFn: configApi.getClipModelTypes,
    staleTime: Infinity,
  })
}

export const useLoraOptions = () => {
  return useQuery({
    queryKey: ['config', 'lora-options'],
    queryFn: configApi.getLoraOptions,
    staleTime: Infinity,
  })
}
