import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'
import { chromium } from 'playwright-core'

const frontendDir = new URL('..', import.meta.url).pathname.replace(/^\//, '').replaceAll('/', '\\')
const baseUrl = 'http://localhost:5181'
const browserPath = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
let server
let browser

before(async () => {
  server = spawn(process.env.PYTHON || 'python', ['-m', 'http.server', '5181', '--bind', '127.0.0.1'], { cwd: frontendDir, stdio: 'ignore', windowsHide: true })
  let ready = false
  for (let i = 0; i < 50; i++) {
    try { const response = await fetch(baseUrl); if (response.ok) { ready = true; break } } catch { await delay(100) }
    await delay(100)
  }
  assert.equal(ready, true, 'frontend preview server did not start')
  browser = await chromium.launch({ executablePath: browserPath, headless: true, args: ['--no-first-run'] })
})

after(async () => {
  await browser?.close()
  if (server && !server.killed) server.kill()
})

async function openApp({ reportStatus = 201, disconnected = false, scheduleEnabled = false, stopsUnavailable = false, liveStatus = 'NOT_CONFIGURED', liveVehicles = [] } = {}) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' })
  const page = await context.newPage()
  page.setDefaultTimeout(7000)
  page.setDefaultNavigationTimeout(7000)
  let submittedReports = 0
  let nearbyLookup = null
  await context.route('http://localhost:8000/**', async route => {
    if (disconnected) return route.abort('failed')
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    let response
    if (path === '/api/v1/system/capabilities') response = { scheduled_journey_search: scheduleEnabled, historical_ticket_analytics: true, community_reporting: true }
    else if (path === '/api/v1/realtime/status') response = { status: liveStatus, configured: liveStatus !== 'NOT_CONFIGURED', authorized: false, current_vehicle_count: liveVehicles.length, stale_vehicle_count: liveVehicles.length, last_attempt_at: null, last_success_at: liveVehicles.length ? '2026-11-18T06:00:00Z' : null, feed_timestamp: null, last_error_code: liveStatus === 'ERROR' ? 'NETWORK_ERROR' : null, generated_at: '2026-11-18T06:01:00Z', data_source: 'test fixture' }
    else if (path === '/api/v1/vehicles/live') response = { status: liveStatus, generated_at: '2026-11-18T06:01:00Z', last_success_at: liveVehicles.length ? '2026-11-18T06:00:00Z' : null, vehicles: liveVehicles, data_source: 'test fixture' }
    else if (path === '/api/v1/stops/nearby' && request.method() === 'POST') { nearbyLookup = { url: request.url(), body: request.postDataJSON() }; response = { items: [{ id: 'gtfs-near-1', stop_name: 'Nearest GTFS Stop', coordinates: { latitude: 28.61, longitude: 77.21 }, distance_meters: 42 }], source: 'test fixture', generated_at: '2026-11-18T06:00:00Z', privacy_note: 'Location used once and not stored.' } }
    else if (path === '/api/v1/journeys/search' && request.method() === 'POST') response = {
      options: [{
        legs: [{ trip_id: 'trip-1', route_id: 'route-1', route_name: 'Route 101', from_stop: { stop_id: 'etm_rohini', stop_name: 'Rohini Sec 22 Terminal' }, to_stop: { stop_id: 'etm_azadpur', stop_name: 'Azadpur Terminal' }, departure_datetime: '2026-11-18T13:00:00+05:30', arrival_datetime: '2026-11-18T13:40:00+05:30', stop_sequence: ['etm_rohini', 'etm_azadpur'] }],
        departure_datetime: '2026-11-18T13:00:00+05:30', arrival_datetime: '2026-11-18T13:40:00+05:30', duration_seconds: 2400, waiting_seconds: 300, transfers: 0, transfer_stops: [], eta_source: 'static_gtfs_schedule', crowd_status: 'unavailable', score: 1, score_components: {},
      }], origin_stop_id: 'etm_rohini', destination_stop_id: 'etm_azadpur', preference: 'balanced', data_source: 'GTFS static schedule', data_status: 'scheduled', generated_at: '2026-11-18T07:00:00Z', crowd_data_available: false, ranking_note: 'scheduled', walking_connections_available: false, message: null,
    }
    else if (path === '/api/v1/stops' && stopsUnavailable) response = { detail: 'ETM has not been processed yet' }
    else if (path === '/api/v1/stops') {
      const q = (url.searchParams.get('q') || '').toLowerCase()
      const stop = q.includes('azadpur')
        ? { id: 'etm_azadpur', stop_name: 'Azadpur Terminal', coordinates: null, demand_available: true }
        : { id: 'etm_rohini', stop_name: 'Rohini Sec 22 Terminal', coordinates: null, demand_available: true }
      response = { items: [stop], source: 'ETM labels', total_returned: 1 }
    } else if (path === '/api/v1/stops/etm_rohini') response = { id: 'etm_rohini', stop_name: 'Rohini Sec 22 Terminal', coordinates: null, data_source: 'ETM', data_status: 'historical', passenger_volume: 25, transaction_count: 9, routes_observed: 2 }
    else if (path === '/api/v1/stops/etm_rohini/demand') response = { stop_id: 'etm_rohini', stop_name: 'Rohini Sec 22 Terminal', passenger_volume: 25, transaction_count: 9, status: 'historical', data_source: 'October dataset', timestamp_basis: 'transaction time', days_covered: 2, observations: [{ transaction_hour: 8, passenger_volume: 15 }, { transaction_hour: 9, passenger_volume: 10 }] }
    else if (path === '/api/v1/crowding/stop/etm_rohini') response = { stop_id: 'etm_rohini', stop_name: 'Rohini Sec 22 Terminal', status: 'UNAVAILABLE', crowd_category: null, report_count: 0, limitations: [] }
    else if (path === '/api/v1/reports/stop/etm_rohini') response = { stop_id: 'etm_rohini', status: 'UNAVAILABLE', report_count: 0, reports: [], limitations: [] }
    else if (path === '/api/v1/analytics/overview') response = { dataset_rows: 100, dataset_min_timestamp: '2026-10-01T00:00:00+05:30', dataset_max_timestamp: '2026-10-30T00:00:00+05:30', distinct_routes: 4, data_source: 'October ETM', data_status: 'historical' }
    else if (path === '/api/v1/analytics/trends') response = { points: [{ period: '2026-10-01', passenger_volume: 30, transaction_count: 10 }], data_source: 'October ETM', data_status: 'historical' }
    else if (path === '/api/v1/analytics/corridors') response = { routes: [], data_source: 'October ETM', data_status: 'historical' }
    else if (path === '/api/v1/reports/crowd' && request.method() === 'POST') {
      submittedReports++
      response = reportStatus === 201
        ? { report_id: 'mock-report', stop_id: 'etm_rohini', stop_name: 'Rohini Sec 22 Terminal', category: 'high', observed_at: '2026-11-18T12:00:00+05:30', created_at: '2026-11-18T12:00:00+05:30', expires_at: '2026-11-18T12:20:00+05:30', status: 'COMMUNITY_REPORTED', observation_type: 'subjective_category_not_headcount', stop_identity_status: 'unreviewed_etm_stop_label' }
        : reportStatus === 429 ? { detail: { code: 'RATE_LIMITED', message: 'Too many reports. Please try again later.' } }
          : { detail: { code: 'DUPLICATE_REPORT', message: 'A recent report from this app is already active for this stop.' } }
    } else response = { detail: 'Unexpected request in browser test' }
    const status = path === '/api/v1/stops' && stopsUnavailable ? 503 : path === '/api/v1/reports/crowd' && reportStatus !== 201 ? reportStatus : 200
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(response) })
  })
  await page.goto(`${baseUrl}/`)
  return { context, page, getSubmittedReports: () => submittedReports, getNearbyLookup: () => nearbyLookup }
}

async function selectStop(page, label, query) {
  const input = page.getByRole('textbox', { name: label })
  await input.fill(query)
  await page.getByRole('button', { name: query, exact: true }).waitFor()
  await page.getByRole('button', { name: query, exact: true }).click()
}

test('mobile journey, stop, crowd report, local rides, insights and account states', async () => {
  const { context, page, getSubmittedReports } = await openApp()
  try {
    await page.getByRole('heading', { name: 'Where to today?' }).waitFor()
    await assert.doesNotReject(page.getByText(/Scheduled journey search is currently unavailable/).waitFor())
    assert.equal(await page.getByText('102A Express').count(), 0)
    await selectStop(page, 'ORIGIN POINT', 'Rohini Sec 22 Terminal')
    await selectStop(page, 'DESTINATION', 'Azadpur Terminal')
    await page.getByRole('button', { name: /FIND YOUR ORBIT/ }).click()
    await page.getByText('Journey planning unavailable').waitFor()
    assert.equal(await page.getByText('102A Express').count(), 0)

    await page.getByRole('link', { name: /Stops/ }).click()
    await page.getByText('Historical demand activity').waitFor()
    await page.getByText(/ticketed passenger-volume records/).waitFor()
    await page.getByText(/does not mean the stop is uncrowded/).waitFor()

    await page.getByRole('link', { name: 'Report' }).click()
    await page.getByRole('button', { name: /Crowded/ }).click()
    const submit = page.getByRole('button', { name: /SHARE UPDATE WITH COMMUTERS/ })
    assert.equal(await submit.isEnabled(), true)
    await submit.click()
    await page.getByText('Thanks for helping riders').waitFor()
    assert.equal(getSubmittedReports(), 1)

    await page.getByRole('link', { name: /Your rides/ }).click()
    await page.getByRole('heading', { name: 'No saved journeys yet' }).waitFor()
    await page.getByRole('button', { name: 'Back' }).click()
    await page.getByRole('button', { name: 'Account' }).click()
    await page.getByText('Accounts are not available yet.').waitFor()
    assert.equal(await page.locator('input[type="password"]').count(), 0)

    await page.getByRole('button', { name: 'Back' }).click()
    await page.getByRole('button', { name: 'Operator insights' }).click()
    await page.getByText('Ticket activity overview').waitFor()
    await page.reload()
    await page.getByText('Ticket activity overview').waitFor()
    await page.setViewportSize({ width: 1440, height: 900 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
  } finally { await context.close() }
})

test('duplicate report response stays a failure and never shows success', async () => {
  const { context, page, getSubmittedReports } = await openApp({ reportStatus: 409 })
  try {
    await selectStop(page, 'ORIGIN POINT', 'Rohini Sec 22 Terminal')
    await page.getByRole('link', { name: 'Report' }).click()
    await page.getByRole('button', { name: /Crowded/ }).click()
    await page.getByRole('button', { name: /SHARE UPDATE WITH COMMUTERS/ }).click()
    await page.getByText(/recent report from this app is already active/).waitFor()
    assert.equal(await page.getByText('Thanks for helping riders').count(), 0)
    assert.equal(getSubmittedReports(), 1)
  } finally { await context.close() }
})

test('arbitrary stop text is rejected until the rider selects a backend result', async () => {
  const { context, page } = await openApp()
  try {
    await page.getByRole('textbox', { name: 'ORIGIN POINT' }).fill('Imaginary station')
    await page.getByRole('button', { name: /FIND YOUR ORBIT/ }).click()
    await page.getByText('Choose both stops from the suggestion list.').waitFor()
    assert.doesNotMatch(page.url(), /#results$/)
  } finally { await context.close() }
})

test('rate-limited report remains a failure with clear feedback', async () => {
  const { context, page, getSubmittedReports } = await openApp({ reportStatus: 429 })
  try {
    await selectStop(page, 'ORIGIN POINT', 'Rohini Sec 22 Terminal')
    await page.getByRole('link', { name: 'Report' }).click()
    await page.getByRole('button', { name: /Crowded/ }).click()
    await page.getByRole('button', { name: /SHARE UPDATE WITH COMMUTERS/ }).click()
    await page.getByText('Report limit reached. Please try again later.').waitFor()
    assert.equal(await page.getByText('Thanks for helping riders').count(), 0)
    assert.equal(getSubmittedReports(), 1)
  } finally { await context.close() }
})

test('only a backend-confirmed journey can be saved and removed from this device', async () => {
  const { context, page } = await openApp({ scheduleEnabled: true })
  try {
    await selectStop(page, 'ORIGIN POINT', 'Rohini Sec 22 Terminal')
    await selectStop(page, 'DESTINATION', 'Azadpur Terminal')
    await page.getByRole('button', { name: /FIND YOUR ORBIT/ }).click()
    await page.getByText('Route 101').first().waitFor()
    await page.getByRole('button', { name: /VIEW JOURNEY DETAILS/ }).click()
    await page.getByText('Scheduled itinerary').waitFor()
    await page.getByRole('button', { name: 'Save journey' }).click()
    await page.getByRole('link', { name: /Your rides/ }).click()
    await page.getByText('SAVED SCHEDULED JOURNEY · THIS DEVICE').waitFor()
    await page.getByRole('button', { name: 'Remove' }).click()
    await page.getByRole('heading', { name: 'No saved journeys yet' }).waitFor()
  } finally { await context.close() }
})

test('backend outage produces a visible connection state', async () => {
  const { context, page } = await openApp({ disconnected: true })
  try {
    await page.getByText(/Backend status unavailable/).waitFor()
    await page.getByRole('button', { name: /Retry connection/ }).waitFor()
  } finally { await context.close() }
})

test('stop search distinguishes missing local data from a backend connection failure', async () => {
  const { context, page } = await openApp({ stopsUnavailable: true })
  try {
    await page.getByRole('textbox', { name: 'ORIGIN POINT' }).fill('Ma')
    await page.getByText(/Stop data is not installed/).waitFor()
    await page.getByText(/validated static GTFS/).waitFor()
  } finally { await context.close() }
})

test('live map shows a clear not-configured state', async () => {
  const { context, page } = await openApp()
  try {
    await page.getByRole('link', { name: 'Live map' }).click()
    await page.getByText('NOT CONFIGURED', { exact: true }).waitFor()
    await page.getByText(/Live bus positions need DELHI_GTFS_RT_API_KEY configured on the backend/).waitFor()
    assert.equal(await page.locator('.live-marker').count(), 0)
  } finally { await context.close() }
})

test('live map labels stale cached vehicle positions and provider-only route IDs', async () => {
  const { context, page } = await openApp({ liveStatus: 'ERROR', liveVehicles: [{
    vehicle_id: 'fixture-bus-1', trip_id: null, route_id: 'provider-route-7', latitude: 28.61, longitude: 77.21,
    bearing: null, speed_meters_per_second: null, current_stop_id: null, current_stop_sequence: null, current_status: null,
    route_id_match_status: 'PROVIDER_ID_ONLY',
    position_timestamp: '2026-11-18T05:55:00Z', feed_timestamp: '2026-11-18T06:00:00Z', freshness_seconds: 360,
    status: 'STALE_CACHED', data_source: 'test fixture',
  }] })
  try {
    await page.getByRole('link', { name: 'Live map' }).click()
    await page.getByText('ERROR', { exact: true }).waitFor()
    await page.locator('.live-marker').waitFor()
    await page.locator('.live-marker').click()
    await page.getByText('Vehicle fixture-bus-1').waitFor()
    await page.getByText(/Provider route ID: provider-route-7 \(not linked to validated static GTFS\)/).waitFor()
    assert.equal(await page.getByText(/last-known cached observations/).count(), 1)
  } finally { await context.close() }
})

test('current location is requested by the rider and sent once only to the nearest-stop API', async () => {
  const { context, page, getNearbyLookup } = await openApp()
  try {
    await context.grantPermissions(['geolocation'], { origin: baseUrl })
    await context.setGeolocation({ latitude: 28.61, longitude: 77.21, accuracy: 12 })
    await page.getByRole('button', { name: 'Use my current location' }).click()
    await page.getByRole('textbox', { name: 'ORIGIN POINT' }).waitFor()
    await page.getByRole('textbox', { name: 'ORIGIN POINT' }).waitFor({ state: 'visible' })
    await page.waitForFunction(() => document.querySelector('[data-stop-field="origin"]').value === 'Nearest GTFS Stop')
    const lookup=getNearbyLookup()
    assert.equal(new URL(lookup.url).search, '')
    assert.deepEqual(lookup.body, { latitude: 28.61, longitude: 77.21 })
  } finally { await context.close() }
})
