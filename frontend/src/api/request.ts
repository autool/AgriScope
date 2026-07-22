import { message } from 'ant-design-vue'
import axios, {
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

interface ApiEnvelope<T> {
  code: number
  data: T
  msg?: string
}

declare module 'axios' {
  interface AxiosRequestConfig {
    silent?: boolean
  }

  interface InternalAxiosRequestConfig {
    silent?: boolean
  }
}

const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
})

axiosInstance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => config,
  () => {
    message.error('请求发送失败，请稍后重试')
    return Promise.reject(new Error('请求发送失败'))
  },
)

axiosInstance.interceptors.response.use(
  (response) => {
    return response
  },
  (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      message.error('系统繁忙，请稍后重试')
      return Promise.reject(new Error('接口请求失败'))
    }
    const status = error.response?.status
    const silent = error.config?.silent === true
    const responseData = error.response?.data as { msg?: string } | undefined
    const safeMessage = responseData?.msg
    if (silent) {
      return Promise.reject(new Error(safeMessage || '接口请求失败'))
    }
    if (status === 404) {
      message.error(safeMessage || '该坐标不在基本农田保护范围内')
    } else if (status === 403) {
      message.error(safeMessage || '当前用户无权执行此操作')
    } else if (status === 422 || status === 400) {
      message.error(safeMessage || '查询参数不合法')
    } else if (error.code === 'ECONNABORTED') {
      message.error('请求超时，请检查网络后重试')
    } else {
      message.error('系统繁忙，请稍后重试')
    }
    return Promise.reject(new Error(safeMessage || '接口请求失败'))
  },
)

const isBinaryResponse = (config?: AxiosRequestConfig): boolean => (
  config?.responseType === 'blob' || config?.responseType === 'arraybuffer'
)

const unwrapResponse = <T>(body: unknown, config?: AxiosRequestConfig): T => {
  if (isBinaryResponse(config)) return body as T
  if (
    typeof body !== 'object'
    || body === null
    || !('code' in body)
    || typeof (body as Partial<ApiEnvelope<T>>).code !== 'number'
    || !('data' in body)
  ) {
    message.error('服务响应不符合统一接口契约')
    throw new Error('服务响应缺少 code/data 包络')
  }
  const envelope = body as ApiEnvelope<T>
  if (envelope.code !== 200) {
    message.error(envelope.msg || '服务响应异常')
    throw new Error(envelope.msg || '业务请求失败')
  }
  return envelope.data
}

const request = {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return axiosInstance
      .get<unknown>(url, config)
      .then((response) => unwrapResponse<T>(response.data, config))
  },
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return axiosInstance
      .post<unknown>(url, data, config)
      .then((response) => unwrapResponse<T>(response.data, config))
  },
  patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return axiosInstance
      .patch<unknown>(url, data, config)
      .then((response) => unwrapResponse<T>(response.data, config))
  },
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return axiosInstance
      .delete<unknown>(url, config)
      .then((response) => unwrapResponse<T>(response.data, config))
  },
}

export default request
