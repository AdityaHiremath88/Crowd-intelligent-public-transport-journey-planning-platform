import test from 'node:test'
import assert from 'node:assert/strict'

globalThis.window = { YUKTIX_API_BASE: 'https://api.example.test/' }
const { api } = await import('../api.js')

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

test('GTFS stop lookup uses v2 fields and encodes user input', async () => {
  const previousFetch = globalThis.fetch
  let requestedUrl
  globalThis.fetch = async url => {
    requestedUrl = String(url)
    return jsonResponse({ items: [{ stop_id: 'stop-1', stop_name: 'A&B', latitude: 28.6, longitude: 77.2, coordinate_source: 'gtfs_publisher_unverified' }] })
  }
  try {
    const result = await api.searchStops('North & West', 8)
    assert.deepEqual(result[0], { id: 'stop-1', stop_name: 'A&B', coordinates: { latitude: 28.6, longitude: 77.2 }, coordinate_source: 'gtfs_publisher_unverified' })
    assert.equal(requestedUrl, 'https://api.example.test/api/v2/stops?q=North%20%26%20West&limit=8')
  } finally { globalThis.fetch = previousFetch }
})

test('route lookup reads the current v2 route contract', async () => {
  const previousFetch = globalThis.fetch
  let requestedUrl
  globalThis.fetch = async url => {
    requestedUrl = String(url)
    return jsonResponse({ items: [{ route_id: 'route/1', route_name: '534DOWN', scheduled_trip_count: 32 }] })
  }
  try {
    const result = await api.searchRoutes('534', 4)
    assert.equal(result[0].route_id, 'route/1')
    assert.equal(requestedUrl, 'https://api.example.test/api/v2/routes?q=534&limit=4')
  } finally { globalThis.fetch = previousFetch }
})

test('stop reports are read from the v2 endpoint with encoded stop IDs', async () => {
  const previousFetch = globalThis.fetch
  let requestedUrl
  globalThis.fetch = async url => {
    requestedUrl = String(url)
    return jsonResponse({ stop_id: 'stop/with space', status: 'UNAVAILABLE', report_count: 0, reports: [] })
  }
  try {
    const result = await api.reportsAtStop('stop/with space')
    assert.equal(result.status, 'UNAVAILABLE')
    assert.equal(requestedUrl, 'https://api.example.test/api/v2/reports/stop/stop%2Fwith%20space')
  } finally { globalThis.fetch = previousFetch }
})

test('crowd report submission sends the v2 contract and deduplication header', async () => {
  const previousFetch = globalThis.fetch
  let call
  globalThis.fetch = async (url, options) => {
    call = { url: String(url), options }
    return jsonResponse({ report_id: 'r-1', status: 'accepted' }, 201)
  }
  const body = { stop_id: 'stop-1', category: 'moderate', observed_at: '2026-11-18T12:00:00+05:30', route_id: null, feedback_code: null }
  try {
    const result = await api.submitReport(body, 'random-client-token')
    assert.equal(result.report_id, 'r-1')
    assert.equal(call.url, 'https://api.example.test/api/v2/reports/crowd')
    assert.equal(call.options.method, 'POST')
    assert.equal(call.options.headers['X-CrowdWise-Client'], 'random-client-token')
    assert.deepEqual(JSON.parse(call.options.body), body)
  } finally { globalThis.fetch = previousFetch }
})

test('structured API errors preserve status and safe detail text', async () => {
  const previousFetch = globalThis.fetch
  globalThis.fetch = async () => jsonResponse({ detail: { code: 'SCHEDULE_UNAVAILABLE', message: 'No validated timetable is loaded.' } }, 503)
  try {
    await assert.rejects(api.journeySearchV2({}), error => error.status === 503 && error.code === 'SCHEDULE_UNAVAILABLE' && error.message === 'No validated timetable is loaded.')
  } finally { globalThis.fetch = previousFetch }
})

test('network failures are returned as a readable connection error', async () => {
  const previousFetch = globalThis.fetch
  globalThis.fetch = async () => { throw new TypeError('socket details should not reach the UI') }
  try {
    await assert.rejects(api.health(), error => error.status === 0 && error.code === 'NETWORK_ERROR' && error.message.includes('Check that the backend is running'))
  } finally { globalThis.fetch = previousFetch }
})

test('malformed API JSON is not treated as an empty success response', async () => {
  const previousFetch = globalThis.fetch
  globalThis.fetch = async () => new Response('not-json', { status: 200 })
  try {
    await assert.rejects(api.health(), error => error.status === 200 && error.code === 'INVALID_RESPONSE')
  } finally { globalThis.fetch = previousFetch }
})
