import axios from 'axios'
import { getMemberName, getProjectId } from './identity'

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use(config => {
  const member = getMemberName()
  const project = getProjectId()
  if (member) config.headers['X-Member-Name'] = member
  if (project) config.headers['X-Project-Id'] = project
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)
