import { message } from 'ant-design-vue'
import axios, {
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

interface ApiEnvelope<T> {
  code: number
  data?: T
  msg?: string
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
    const responseData = error.response?.data as { msg?: string } | undefined
    const safeMessage = responseData?.msg
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

const unwrapResponse = <T>(body: ApiEnvelope<T> | T): T => {
  if (
    typeof body === 'object'
    && body !== null
    && 'code' in body
    && typeof (body as ApiEnvelope<T>).code === 'number'
  ) {
    const envelope = body as ApiEnvelope<T>
    if (envelope.code !== 200 || envelope.data === undefined) {
      message.error(envelope.msg || '服务响应异常')
      throw new Error(envelope.msg || '业务请求失败')
    }
    return envelope.data
  }
  // 兼容尚未迁移为统一成功包络的存量接口，后端迁移完成后删除此分支。
  return body as T
}

const request = {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return axiosInstance
      .get<ApiEnvelope<T> | T>(url, config)
      .then((response) => unwrapResponse(response.data))
  },
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return axiosInstance
      .post<ApiEnvelope<T> | T>(url, data, config)
      .then((response) => unwrapResponse(response.data))
  },
  patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return axiosInstance
      .patch<ApiEnvelope<T> | T>(url, data, config)
      .then((response) => unwrapResponse(response.data))
  },
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return axiosInstance
      .delete<ApiEnvelope<T> | T>(url, config)
      .then((response) => unwrapResponse(response.data))
  },
}

export default request
