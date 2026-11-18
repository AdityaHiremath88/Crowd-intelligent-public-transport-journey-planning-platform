const API_BASE = (window.YUKTIX_API_BASE || 'http://localhost:8000').replace(/\/$/, '')
const cache = new Map()
async function request(path, options = {}) {
  const { timeoutMs = 12000, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...fetchOptions, signal: fetchOptions.signal || controller.signal, headers: { Accept: 'application/json', ...(fetchOptions.body ? { 'Content-Type': 'application/json' } : {}), ...(fetchOptions.headers || {}) } })
  } catch (error) {
    if (error.name === 'AbortError') throw Object.assign(new Error('The request timed out. Please try again.'), { status: 0, code: 'TIMEOUT' })
    throw Object.assign(new Error('Cannot reach the Yuktix API. Check that the backend is running.'), { status: 0, code: 'NETWORK_ERROR' })
  } finally { clearTimeout(timer) }
  const payload = await response.json().catch(() => null)
  if (payload === null) throw Object.assign(new Error('The API returned an unreadable response.'), { status: response.status, code: 'INVALID_RESPONSE' })
  if (!response.ok) {
    const detail = payload.detail
    const error = new Error(typeof detail === 'string' ? detail : detail?.message || `Request failed (${response.status})`)
    error.status = response.status
    error.code = detail?.code
    error.payload = payload
    throw error
  }
  return payload
}
export const api = {
  base: API_BASE,
  async health() { return request('/health') },
  async capabilities() { return request('/api/v1/system/capabilities') },
  async searchStops(query, limit = 8) {
    const key = query.trim().toLowerCase()
    if (key.length < 2) return []
    if (cache.has(key)) return cache.get(key)
    const result = await request(`/api/v1/stops?q=${encodeURIComponent(query)}&limit=${limit}`)
    const items = result.items || []
    cache.set(key, items)
    return items
  },
  async stop(stopId) { return request(`/api/v1/stops/${encodeURIComponent(stopId)}`) },
  async demand(stopId) { return request(`/api/v1/stops/${encodeURIComponent(stopId)}/demand`) },
  async crowdAtStop(stopId) { return request(`/api/v1/crowding/stop/${encodeURIComponent(stopId)}`) },
  async reportsAtStop(stopId) { return request(`/api/v1/reports/stop/${encodeURIComponent(stopId)}`) },
  async submitReport(body, clientToken) {
    return request('/api/v1/reports/crowd', { method: 'POST', headers: { 'X-CrowdWise-Client': clientToken }, body: JSON.stringify(body) })
  },
  async journeySearch(body) { return request('/api/v1/journeys/search', { method: 'POST', body: JSON.stringify(body), timeoutMs: 60000 }) },
  async overview() { return request('/api/v1/analytics/overview') },
  async trends() { return request('/api/v1/analytics/trends?granularity=day') },
  async corridors() { return request('/api/v1/analytics/corridors?limit=8') },
  async routeActivity(routeLabel, targetDatetime) {
    const params = new URLSearchParams({ route_label: routeLabel, target_datetime: targetDatetime })
    return request(`/api/v1/analytics/route-activity?${params}`)
  }
}
