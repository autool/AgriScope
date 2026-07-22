import request from './request'

import type {
  FieldVerificationArtifact,
  FieldVerificationArtifactUploadPayload,
} from '@/types/workbench'

/**
 * 上传外业核查照片、语音或调查表实体证据。
 * @param verificationCode 外业记录业务编号。
 * @param payload 上传文件、类型、上传人和证据说明。
 * @returns 已通过服务端实体校验的证据摘要。
 */
export const uploadFieldVerificationArtifact = (
  verificationCode: string,
  payload: FieldVerificationArtifactUploadPayload,
) => {
  const formData = new FormData()
  formData.append('file', payload.file)
  formData.append('artifact_type', payload.artifact_type)
  formData.append('uploader_code', payload.uploader_code)
  formData.append('comment', payload.comment)
  return request.post<FieldVerificationArtifact>(
    `/v1/field-verifications/${verificationCode}/artifacts`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    },
  )
}

/**
 * 下载并触发服务端路径、签名、大小和 SHA-256 复核。
 * @param verificationCode 外业记录业务编号。
 * @param artifactCode 实体证据编号。
 * @param operatorCode 当前项目用户稳定编码。
 * @returns 原始实体文件 Blob。
 */
export const downloadFieldVerificationArtifact = (
  verificationCode: string,
  artifactCode: string,
  operatorCode: string,
) => request.get<Blob>(
  `/v1/field-verifications/${verificationCode}/artifacts/${artifactCode}/download`,
  {
    params: { operator_code: operatorCode },
    responseType: 'blob',
    timeout: 120_000,
  },
)
