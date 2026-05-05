const FALLBACK_API_BASE_URL = 'http://localhost:8000'

export function getApiBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL || FALLBACK_API_BASE_URL).replace(/\/$/, '')
}

async function request(path, options = {}) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = data?.message || `请求失败 (${response.status})`
    throw new Error(message)
  }

  return data
}

export async function fetchHealth() {
  return request('/api/health', {
    method: 'GET',
  })
}

export async function fetchRecommendations(payload) {
  return request('/api/recommend', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
