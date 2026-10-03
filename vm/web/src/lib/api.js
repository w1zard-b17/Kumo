export class ApiError extends Error {
  constructor(status, code, message, data) {
    super(message)
    this.status = status
    this.code = code
    this.data = data
  }
}

let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

function qs(query) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x))
    else p.append(k, v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export async function api(path, { method = 'GET', body, query, signal } = {}) {
  let res
  try {
    res = await fetch(`/api${path}${query ? qs(query) : ''}`, {
      method,
      signal,
      credentials: 'same-origin',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError(0, 'network', 'Kumo is unreachable. Is the VM running?')
  }
  const isJson = (res.headers.get('content-type') || '').includes('json')
  const data = isJson ? await res.json().catch(() => null) : null
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/auth')) onUnauthorized()
    throw new ApiError(res.status, data?.code, data?.message || res.statusText || 'Request failed', data)
  }
  return data
}

export const get = (path, query, opts) => api(path, { query, ...opts })
export const post = (path, body) => api(path, { method: 'POST', body: body ?? {} })
export const patch = (path, body) => api(path, { method: 'PATCH', body })
export const put = (path, body) => api(path, { method: 'PUT', body })
export const del = (path, query) => api(path, { method: 'DELETE', query })
