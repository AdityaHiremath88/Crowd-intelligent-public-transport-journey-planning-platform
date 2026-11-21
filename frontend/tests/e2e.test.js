import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'
import { chromium } from 'playwright-core'

const frontendDir = new URL('..', import.meta.url).pathname.replace(/^\//, '').replaceAll('/', '\\')
const baseUrl = 'http://localhost:5181'
const apiBase = 'http://127.0.0.1:8002'
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

const stops = [
  { stop_id: 'stop-rohini', stop_name: 'Rohini Sec 22 Terminal', latitude: 28.73, longitude: 77.1, coordinate_source: 'gtfs_publisher_unverified' },
  { stop_id: 'stop-azadpur', stop_name: 'Azadpur Terminal', latitude: 28.71, longitude: 77.18, coordinate_source: 'gtfs_publisher_unverified' },
]
const route = { route_id: 'route-534', route_name: '534DOWN', route_long_name: '534DOWN', scheduled_trip_count: 32 }
let submittedReports = 0

function send(routeRequest, body, status = 200) {
  return routeRequest.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function openApp({ reportStatus = 201, disconnected = false } = {}) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' })
  await context.addInitScript(apiOrigin => { window.YUKTIX_API_BASE = apiOrigin }, apiBase)
  await context.route(`${apiBase}/**`, async requestRoute => {
    if (disconnected) return requestRoute.abort('failed')
    const request = requestRoute.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (path === '/api/v2/health') return send(requestRoute, { status: 'ok', service: 'yuktix-backend-v2' })
    if (path === '/api/v2/capabilities') return send(requestRoute, { scheduled_journey_search: true, gtfs_stop_search: true, historical_route_activity: true, estimated_fares: true })
    if (path === '/api/v2/stops') {
      const query = (url.searchParams.get('q') || '').toLowerCase()
      const matches = stops.filter(stop => stop.stop_name.toLowerCase().includes(query))
      return send(requestRoute, { items: matches, source: 'GTFS static feed' })
    }
    if (path === '/api/v2/routes' && request.method() === 'GET') return send(requestRoute, { items: [route] })
    if (path === '/api/v2/routes/route-534') return send(requestRoute, { ...route, headsign: 'Azadpur Terminal', stops: stops.map(({ stop_id, stop_name }) => ({ stop_id, stop_name })), source: 'GTFS static feed' })
    if (path === '/api/v2/routes/route-534/activity') return send(requestRoute, { status: 'available', route_id: route.route_id, transaction_hour: Number(url.searchParams.get('hour') || 8), average_passenger_volume: 23, average_transaction_count: 9, data_source: 'October ETM', data_status: 'historical' })
    if (path === '/api/v2/journeys/search' && request.method() === 'POST') {
      const body = request.postDataJSON()
      const departure = new Date(Date.now() + 2 * 60_000)
      const sourceOptions = body.route_id
        ? [{ route_name: '534DOWN', duration_seconds: 2400, departure_offset: 0, ordinary: 10, ac: 15 }]
        : [
            { route_name: '534DOWN', duration_seconds: 2400, departure_offset: 0, ordinary: 10, ac: 15 },
            { route_name: '534UP', duration_seconds: 1800, departure_offset: 5, ordinary: 15, ac: 25 },
          ]
      const options = sourceOptions.map(item => {
        const start = new Date(departure.getTime() + item.departure_offset * 60_000).toISOString()
        const end = new Date(Date.parse(start) + item.duration_seconds * 1000).toISOString()
        return {
          legs: [{ trip_id: `trip-${item.route_name}`, route_id: 'route-534', route_name: item.route_name, from_stop: { stop_id: body.origin_stop_id, stop_name: stops[0].stop_name }, to_stop: { stop_id: body.destination_stop_id, stop_name: stops[1].stop_name }, departure_datetime: start, arrival_datetime: end, stop_sequence: ['stop-rohini', 'stop-azadpur'], eta_source: 'GTFS static schedule', fare_estimate: { status: 'estimated', ordinary_adult_fare_inr: item.ordinary, ac_adult_fare_inr: item.ac, estimated_distance_km: 8.2 } }],
          departure_datetime: start, arrival_datetime: end, duration_seconds: item.duration_seconds, waiting_seconds: 60, transfers: 0, transfer_stops: [], fare_estimate: { status: 'estimated', currency: 'INR', estimated_leg_count: 1, total_leg_count: 1, ordinary_adult_total_inr: item.ordinary, ac_adult_total_inr: item.ac, estimated_distance_km: 8.2 }, eta_source: 'GTFS static schedule', crowd_status: 'unavailable', score: 1, score_components: {},
        }
      })
      return send(requestRoute, { options, origin_stop_id: body.origin_stop_id, destination_stop_id: body.destination_stop_id, preference: body.preference, data_source: 'GTFS static schedule', data_status: 'scheduled', generated_at: new Date().toISOString(), crowd_data_available: false })
    }
    if (path === '/api/v2/crowding/stop/stop-rohini') return send(requestRoute, { stop_id: 'stop-rohini', status: 'UNAVAILABLE', crowd_category: null, report_count: 0, limitations: [] })
    if (path === '/api/v2/reports/stop/stop-rohini') return send(requestRoute, { stop_id: 'stop-rohini', status: 'UNAVAILABLE', report_count: 0, reports: [], limitations: [] })
    if (path === '/api/v2/reports/crowd' && request.method() === 'POST') {
      submittedReports++
      if (reportStatus !== 201) {
        const status = reportStatus
        const code = status === 429 ? 'RATE_LIMITED' : 'DUPLICATE_REPORT'
        const message = status === 429 ? 'Too many reports. Please try again later.' : 'A recent report from this app is already active for this stop.'
        return send(requestRoute, { detail: { code, message } }, status)
      }
      return send(requestRoute, { report_id: 'mock-report', stop_id: 'stop-rohini', stop_name: stops[0].stop_name, category: 'high', observed_at: new Date().toISOString(), created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 20 * 60_000).toISOString(), status: 'COMMUNITY_REPORTED', observation_type: 'subjective_category_not_headcount' }, 201)
    }
    return send(requestRoute, { detail: `Unexpected test request: ${request.method()} ${path}` }, 404)
  })
  const page = await context.newPage()
  page.setDefaultTimeout(5000)
  await page.goto(`${baseUrl}/`)
  return { context, page }
}

async function selectStop(page, label, query) {
  await page.getByRole('textbox', { name: label, exact: true }).fill(query)
  const suggestion = page.locator(`[data-suggestions="${label === 'ORIGIN POINT' ? 'origin' : 'destination'}"] button`).first()
  await suggestion.waitFor()
  await suggestion.click()
}

async function planJourney(page) {
  await page.getByRole('heading', { name: 'Plan your smart journey' }).waitFor()
  await selectStop(page, 'ORIGIN POINT', 'Rohini')
  await selectStop(page, 'DESTINATION', 'Azadpur')
  await page.getByRole('button', { name: /FIND SMART JOURNEY/ }).click()
  await page.locator('article.result-option').first().waitFor()
}

test('journey search, fare, preference sorting, details, and crowd handoff', async () => {
  const { context, page } = await openApp()
  try {
    await planJourney(page)
    assert.equal(await page.locator('article.result-option').count(), 2)
    assert.equal(await page.getByText('₹10 / ₹15').count(), 1)
    await page.getByRole('button', { name: 'Fastest', exact: true }).click()
    await page.getByRole('button', { name: 'Comfort', exact: true }).click()
    assert.equal(await page.locator('.filter-tab.active').innerText(), 'Comfort')
    await page.getByRole('button', { name: /VIEW JOURNEY DETAILS/ }).first().click()
    await page.getByText('Scheduled itinerary').waitFor()
    await page.getByText('Ordinary / AC · est.').waitFor()
    await page.getByRole('button', { name: /View crowd status for this route/ }).click()
    await page.getByRole('heading', { name: 'Crowd Insights' }).waitFor()
    assert.match(await page.locator('[data-crowd-route-query]').evaluate(input => input.value), /^534/)
    await page.getByText(/From Rohini Sec 22 Terminal/).waitFor()
    await page.getByText('Historical ticket activity').waitFor()
    await page.getByText('23 avg passengers').waitFor()
  } finally { await context.close() }
})

test('bus route search loads the selected GTFS route and stop choices', async () => {
  const { context, page } = await openApp()
  try {
    await page.getByRole('textbox', { name: 'Search bus route' }).fill('534')
    const match = page.locator('[data-route-suggestions] button').first()
    await match.waitFor()
    await match.click()
    await page.getByRole('combobox', { name: 'BOARD AT' }).waitFor()
    assert.equal(await page.getByRole('combobox', { name: 'GET OFF AT' }).locator('option').count(), 2)
    await page.getByRole('button', { name: /FIND JOURNEYS ON ROUTE/ }).click()
    await page.locator('article.result-option').first().waitFor()
    assert.ok((await page.locator('article.result-option').first().innerText()).includes('534DOWN'))
  } finally { await context.close() }
})

test('crowd report success and duplicate/rate limit responses are handled honestly', async t => {
  for (const scenario of [{ status: 201, success: true }, { status: 409, success: false }, { status: 429, success: false }]) {
    await t.test(`report response ${scenario.status}`, async () => {
      submittedReports = 0
      const { context, page } = await openApp({ reportStatus: scenario.status })
      try {
        await planJourney(page)
        await page.getByRole('button', { name: /VIEW JOURNEY DETAILS/ }).first().click()
        await page.getByRole('button', { name: /Report crowding at a stop/ }).click()
    await page.locator('[data-action="crowd-category"][data-value="high"]').click()
        await page.getByRole('button', { name: /SHARE UPDATE WITH COMMUTERS/ }).click()
        assert.equal(submittedReports, 1)
        if (scenario.success) await page.getByText('Thanks for helping riders').waitFor()
        else {
          assert.equal(await page.getByText('Thanks for helping riders').count(), 0)
          const retryButton = page.getByRole('button', { name: /SHARE UPDATE WITH COMMUTERS/ })
          await retryButton.waitFor()
          assert.equal(await retryButton.isEnabled(), true)
          assert.match(await retryButton.innerText(), /SHARE UPDATE WITH COMMUTERS/)
          assert.doesNotMatch(await retryButton.innerText(), /SENDING/)
          await page.getByText(scenario.status === 409 ? /recent report from this app is already active/ : /Report limit reached/).waitFor()
        }
      } finally { await context.close() }
    })
  }
})

test('unselected free text cannot be submitted as a journey stop', async () => {
  const { context, page } = await openApp()
  try {
    await page.getByRole('textbox', { name: 'ORIGIN POINT', exact: true }).fill('Imaginary station')
    await page.getByRole('textbox', { name: 'DESTINATION', exact: true }).fill('Azadpur')
    await page.getByRole('button', { name: /FIND SMART JOURNEY/ }).click()
    await page.getByText('Choose both stops from the suggestion list.').waitFor()
    assert.doesNotMatch(page.url(), /#results$/)
  } finally { await context.close() }
})

test('backend outage renders the connection state without crashing the app', async () => {
  const { context, page } = await openApp({ disconnected: true })
  try {
    await page.getByRole('heading', { name: 'Plan your smart journey' }).waitFor()
    await page.getByRole('textbox', { name: 'ORIGIN POINT', exact: true }).fill('Rohini')
    await page.getByText('Stop search is unavailable. Check the backend connection.').waitFor()
    assert.match(await page.title(), /Yuktix/)
  } finally { await context.close() }
})
