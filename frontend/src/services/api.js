const FALLBACK_API_BASE_URL = 'http://localhost:8000'
// 默认请求超时 30s（LLM 解析最长 10s，推荐接口最长约 15s，留足余量）
const DEFAULT_TIMEOUT_MS = 30000

export function getApiBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL || FALLBACK_API_BASE_URL).replace(/\/$/, '')
}

/**
 * 带超时的 fetch 封装。
 * @param {string} path
 * @param {object} options - fetch options，可额外传入 timeout 覆盖默认超时
 * @returns {Promise<any>}
 */
async function request(path, options = {}) {
  const { timeout, ...fetchOptions } = options
  const controller = new AbortController()
  const timeoutMs = timeout ?? DEFAULT_TIMEOUT_MS
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
      ...fetchOptions,
    })

    const data = await response.json().catch(() => null)

    if (!response.ok) {
      const message = data?.message || `请求失败 (${response.status})`
      throw new Error(message)
    }

    return data
  } finally {
    clearTimeout(timer)
  }
}

export async function fetchHealth() {
  return request('/api/health', {
    method: 'GET',
  })
}

export async function fetchParseIntent(payload) {
  return request('/api/parse-intent', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchRecommendations(payload) {
  return request('/api/recommend', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchPresetRecommendations(payload) {
  return request('/api/preset-recommend', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchSpeeches(resultId) {
  return request(`/api/speeches/${resultId}`, {
    method: 'GET',
  })
}

export async function submitFeedback(payload) {
  return request('/api/feedback', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
