import request from '@/api/request'

export interface SystemHealth {
  status: 'ok'
  database: 'connected'
}

export const getSystemHealth = () => request.get<SystemHealth>(
  '/v1/system-health',
  { silent: true, timeout: 5000 },
)
