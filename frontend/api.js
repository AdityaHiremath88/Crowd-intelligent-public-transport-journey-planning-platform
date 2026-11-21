const API_BASE = (window.YUKTIX_API_BASE || 'http://127.0.0.1:8002').replace(/\/$/, '')
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
  async capabilities() { return request('/api/v2/capabilities') },
  async searchJourneyStops(query, limit = 8) {
    const key = query.trim().toLowerCase()
    if (key.length < 2) return []
    const result = await request(`/api/v2/stops?q=${encodeURIComponent(query)}&limit=${limit}`)
    return (result.items || []).map(stop => ({
      id: stop.stop_id,
      stop_name: stop.stop_name,
      coordinates: stop.latitude == null || stop.longitude == null ? null : { latitude: stop.latitude, longitude: stop.longitude },
      coordinate_source: stop.coordinate_source,
    }))
  },
  async searchRoutes(query, limit = 12) {
    const key = query.trim()
    if (key.length < 1) return []
    const result = await request(`/api/v2/routes?q=${encodeURIComponent(key)}&limit=${limit}`)
    return result.items || []
  },
  async route(routeId) { return request(`/api/v2/routes/${encodeURIComponent(routeId)}`) },
  async searchStops(query, limit = 8) {
    return api.searchJourneyStops(query, limit)
  },
  async stop(stopId) { return request(`/api/v2/stops?q=${encodeURIComponent(stopId)}&limit=1`) },
  async demand(stopId) { return request(`/api/v2/stops?q=${encodeURIComponent(stopId)}&limit=1`) },
  async crowdAtStop(stopId) { return request(`/api/v2/crowding/stop/${encodeURIComponent(stopId)}`) },
  async reportsAtStop(stopId) { return request(`/api/v2/reports/stop/${encodeURIComponent(stopId)}`) },
  async submitReport(body, clientToken) {
    return request('/api/v2/reports/crowd', { method: 'POST', headers: { 'X-CrowdWise-Client': clientToken }, body: JSON.stringify(body) })
  },
  async journeySearch(body) { return request('/api/v1/journeys/search', { method: 'POST', body: JSON.stringify(body), timeoutMs: 60000 }) },
  async journeySearchV2(body) { return request('/api/v2/journeys/search', { method: 'POST', body: JSON.stringify(body), timeoutMs: 60000 }) },
  async overview() { return request('/api/v1/analytics/overview') },
  async trends() { return request('/api/v1/analytics/trends?granularity=day') },
  async corridors() { return request('/api/v1/analytics/corridors?limit=8') },
  async routeActivity(routeId, targetDatetime) {
    const localTime = String(targetDatetime).match(/^(\d{4}-\d{2}-\d{2})T(\d{2}):/)
    if (!localTime) throw Object.assign(new Error('The scheduled route time is invalid.'), { code: 'INVALID_ROUTE_TIME' })
    const params = new URLSearchParams({
      target_date: localTime[1],
      hour: String(Number(localTime[2])),
    })
    return request(`/api/v2/routes/${encodeURIComponent(routeId)}/activity?${params}`)
  }
}
