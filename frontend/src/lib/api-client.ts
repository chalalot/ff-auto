import axios from 'axios'
import { getMemberName, getProjectId } from './identity'

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
  // FastAPI reads a repeated key (?provider=a&provider=b) for list params.
  // Axios' default would send provider[]=a&provider[]=b, which arrives as no
  // value at all — a silently unscoped query rather than an error.
  paramsSerializer: { indexes: null },
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
