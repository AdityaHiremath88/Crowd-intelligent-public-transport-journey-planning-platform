import { api } from './api.js'

const app = document.querySelector('#app')
const toastNode = document.querySelector('#toast')
const savedKey = 'yuktix.savedJourneys.v1'
const tokenKey = 'yuktix.reportClient.v1'
const state = { page: location.hash.slice(1) || 'home', origin: null, destination: null, stop: null, reportStop: null, reportRoute: null, preference: 'balanced', departure: new Date(Date.now() + 5 * 60000), reportCategory: null, reportFeedback: null, capabilities: null, capabilityError: null, results: null, selectedJourney: null, stopData: null, stopLoading: false, reportSent: false, operatorData: null, stopError: null, liveStatus: null, liveFeed: null, liveError: null, liveLoading: false, liveLoaded: false, map: null, liveTimer: null }
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[char])
let toastTimer
function toast(message) { toastNode.textContent = message; toastNode.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toastNode.classList.remove('show'), 3200) }
function pageHeader(title, subtitle = '', tools = '') { return `<header class="page-head"><button class="back-btn" data-action="back" aria-label="Back"><span class="material-symbols-outlined">arrow_back</span></button><div class="page-title">${escapeHtml(title)}${subtitle ? `<span class="page-subtitle">${escapeHtml(subtitle)}</span>` : ''}</div><div class="page-tools">${tools}</div></header>` }
function scheduleTime(value) { if(!value)return 'Not provided';const date=new Date(value);return escapeHtml(Number.isNaN(date.getTime())?value:date.toLocaleString([], {dateStyle:'medium',timeStyle:'short'})) }
function brandHeader() { return `<header class="topbar"><a class="brand" href="#home"><span class="brand-mark">C</span><span>CROWDWISE<small>DELHI TRANSIT GRID</small></span></a><div class="header-actions"><button class="icon-btn" data-route="operator" aria-label="Operator insights"><span class="material-symbols-outlined">grid_view</span></button><button class="avatar" data-route="auth" aria-label="Account"><span class="material-symbols-outlined">person</span></button></div></header>` }
function bottomNav() {
  const active = state.page === 'home' ? 'home' : ['results','journey','rides'].includes(state.page) ? 'rides' : state.page === 'live' ? 'live' : state.page === 'stop' ? 'stops' : state.page === 'report' ? 'report' : ''
  return `<nav class="bottom-nav" aria-label="Main navigation"><a class="${active==='home'?'selected':''}" href="#home"><span class="material-symbols-outlined">explore</span>Go</a><a class="${active==='live'?'selected':''}" href="#live"><span class="material-symbols-outlined">map</span>Live map</a><a class="${active==='rides'?'selected':''}" href="#rides"><span class="material-symbols-outlined">all_inclusive</span>Your rides</a><a class="${active==='stops'?'selected':''}" href="#stop"><span class="material-symbols-outlined">location_on</span>Stops</a><a class="${active==='report'?'selected':''}" href="#report"><span class="material-symbols-outlined">flag</span>Report</a></nav>`
}
function liveMapPage() {
  const status=state.liveStatus?.status||state.liveFeed?.status||'UNAVAILABLE'
  const vehicles=state.liveFeed?.vehicles||[]
  const message={NOT_CONFIGURED:'Live bus positions need DELHI_GTFS_RT_API_KEY configured on the backend.',UNAVAILABLE:'The backend has not received a successful feed yet.',STALE:'Showing last-known positions; the provider feed is stale.',ERROR:'The latest provider request failed. Any positions shown are last-known cached observations.',HEALTHY:`${vehicles.length} vehicle position${vehicles.length===1?'':'s'} received from the latest feed.`}[status]||'Live feed status is unavailable.'
  return `${pageHeader('Live bus map','Official GTFS-Realtime positions')}<main class="screen"><section class="live-map-card"><div class="live-feed-summary"><div><span class="live-feed-status" data-status="${escapeHtml(status)}">${escapeHtml(status.replaceAll('_',' '))}</span><p>${escapeHtml(state.liveError||message)}</p><p>${state.liveStatus?.last_success_at?`Last successful fetch: ${scheduleTime(state.liveStatus.last_success_at)}`:'No successful feed fetch recorded.'}</p></div><button class="text-link" data-action="retry-live" ${state.liveLoading?'disabled':''}>${state.liveLoading?'Refreshing…':'Refresh'}</button></div><div id="live-map" class="live-map" role="application" aria-label="Map of buses with valid Delhi Transport Stack GPS positions"></div><p class="live-map-note">Markers use provider GPS coordinates and show their last observation time. Route IDs are shown as provider identifiers unless matched to validated static GTFS. A single position does not indicate direction or movement. Map tiles © OpenStreetMap contributors.</p></section><p class="subtle-note">Feed refresh policy: backend polls every 60 seconds by default. Vehicle Positions do not provide a validated arrival time or passenger count.</p></main>${bottomNav()}`
}
function drawLiveMap() {
  const node=document.getElementById('live-map')
  if(!node)return
  if(!window.L){node.innerHTML='<div class="crowd-state">The map library could not be loaded. Vehicle feed status remains available above; retry when online.</div>';return}
  state.map=window.L.map(node,{scrollWheelZoom:false}).setView([28.6139,77.2090],11)
  const tileUrl=window.CROWDWISE_TILE_URL||window.YUKTIX_TILE_URL||'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
  window.L.tileLayer(tileUrl,{maxZoom:19,attribution:window.CROWDWISE_TILE_ATTRIBUTION||window.YUKTIX_TILE_ATTRIBUTION||'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(state.map)
  const vehicles=state.liveFeed?.vehicles||[]
  const points=[]
  for(const vehicle of vehicles){
    const lat=Number(vehicle.latitude),lon=Number(vehicle.longitude)
    if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat < -90||lat > 90||lon < -180||lon > 180)continue
    const stale=vehicle.status==='STALE_CACHED'||state.liveFeed?.status!=='HEALTHY'
    const icon=window.L.divIcon({className:'',html:`<span class="live-marker ${stale?'stale':''}"><span class="material-symbols-outlined">directions_bus</span></span>`,iconSize:[34,34],iconAnchor:[17,17]})
    const route=vehicle.route_id?(vehicle.route_id_match_status==='VERIFIED_STATIC_GTFS'?`<br>Verified GTFS route ID: ${escapeHtml(vehicle.route_id)}`:`<br>Provider route ID: ${escapeHtml(vehicle.route_id)} (not linked to validated static GTFS)`):'<br>Route: not supplied'
    const stop=vehicle.current_stop_id?`<br>Provider stop ID: ${escapeHtml(vehicle.current_stop_id)}`:''
    const freshness=Number(vehicle.freshness_seconds)
    const age=Number.isFinite(freshness)?`${Math.floor(freshness/60)} min ${freshness%60} sec ago`:'age unavailable'
    const content=`<strong>Vehicle ${escapeHtml(vehicle.vehicle_id)}</strong><br>${stale?'Last-known position':'GPS observation'}: ${scheduleTime(vehicle.position_timestamp)}<br>Position age: ${escapeHtml(age)}${route}${stop}`
    window.L.marker([lat,lon],{icon}).addTo(state.map).bindPopup(content)
    points.push([lat,lon])
  }
  if(points.length)state.map.fitBounds(points,{padding:[28,28],maxZoom:14})
}
async function loadLiveData() {
  if(state.liveLoading)return
  state.liveLoading=true
  try{
    const [feed,status]=await Promise.allSettled([api.liveVehicles(),api.realtimeStatus()])
    state.liveFeed=feed.status==='fulfilled'?feed.value:null
    state.liveStatus=status.status==='fulfilled'?status.value:(feed.status==='fulfilled'?feed.value:null)
    state.liveError=feed.status==='rejected'?feed.reason.message:null
  }finally{state.liveLoaded=true;state.liveLoading=false;if(state.page==='live')render()}
}
function autocomplete(field, label, value, hint = '') {
  return `<label class="location-row ${field}-row"><span class="location-dot ${field==='origin'?'origin-dot':'destination-dot'}"></span><span class="field-copy"><span class="field-label">${label}</span><span class="stop-autocomplete" data-autocomplete="${field}"><input data-stop-field="${field}" value="${escapeHtml(value)}" placeholder="Search a Delhi bus stop" autocomplete="off" aria-label="${label}"><span class="suggestions" data-suggestions="${field}" hidden></span></span><small>${hint}</small></span></label>`
}
function homePage() {
  const originName = state.origin?.stop_name || ''
  const destinationName = state.destination?.stop_name || ''
  return `${brandHeader()}<main class="screen"><section class="hero"><div class="orbit" aria-hidden="true"><i></i><b></b></div><div class="hero-copy"><span class="grid-pill"><i></i>Delhi Transit Grid</span><h1>Where to<br>today?</h1></div></section>
    <section class="search-card" aria-label="Plan your journey">${autocomplete('origin','ORIGIN POINT',originName,'Choose a stop from the static GTFS list')}<button class="text-link location-action" data-action="current-location" ${state.locationLoading?'disabled':''}>${state.locationLoading?'Finding nearest stop…':'Use my current location'}</button><p class="subtle-note">Your browser will ask permission. Coordinates are sent once to find a nearby stop and are not stored.</p>
      <div class="swap-line"><span></span><button class="swap" data-action="swap" aria-label="Swap origin and destination"><span class="material-symbols-outlined">swap_vert</span></button></div>
      ${autocomplete('destination','DESTINATION',destinationName,'Choose a stop from the static GTFS list')}
      <div class="options"><label class="time-chip"><span class="material-symbols-outlined">schedule</span><span>Depart</span><input data-departure type="datetime-local" value="${new Date(state.departure.getTime()-state.departure.getTimezoneOffset()*60000).toISOString().slice(0,16)}" aria-label="Departure date and time"></label><button class="choice-chip ${state.preference==='balanced'?'active':''}" data-action="preference" data-value="balanced"><i></i>Balanced</button><button class="choice-chip ${state.preference==='fastest'?'active':''}" data-action="preference" data-value="fastest"><span class="material-symbols-outlined">bolt</span>Fastest</button><button class="choice-chip ${state.preference==='comfort'?'active':''}" data-action="preference" data-value="comfort"><span class="material-symbols-outlined">accessible</span>Comfort</button></div>
    </section><button class="cta" data-action="search"><span class="cta-label"><span class="material-symbols-outlined">near_me</span>FIND YOUR ORBIT</span><span class="cta-arrow"><span class="material-symbols-outlined">arrow_forward</span></span></button>
    <section class="frequent-section"><span class="kicker">JOURNEY PLANNING</span><div class="crowd-state">${state.capabilityError?`Backend status unavailable: ${escapeHtml(state.capabilityError)}`:state.capabilities?.scheduled_journey_search?'Static Delhi bus schedules are ready. Times are approximate and are not live arrivals.':'Scheduled journey search is currently unavailable because a validated Delhi GTFS timetable is not connected. Stop search and historical stop insights are available.'}</div>${state.capabilityError?'<button class="text-link" data-action="retry-capabilities">Retry connection</button>':''}</section>
    </main>${bottomNav()}`
}
function resultsPage() {
  const options=state.results?.options||[]
  const unavailable=!state.capabilities?.scheduled_journey_search||state.results?.data_status==='unavailable'
  const cards=options.map((journey,index)=>{
    const first=journey.legs?.[0],last=journey.legs?.at(-1)
    const duration=Math.round((journey.duration_seconds||0)/60)
    return `<article class="recommended-card"><div class="route-top"><span class="route-number">${escapeHtml(first?.route_name||first?.route_id||'Scheduled journey')}</span>${index===0?'<span class="recommended-tag">BACKEND RESULT</span>':''}<span class="live-in">${escapeHtml(journey.eta_source||'Scheduled data')}</span></div><div class="trip-grid"><div><div class="trip-duration">${duration}<small> MIN</small></div><div class="trip-kind">${Number(journey.transfers)||0} transfers · scheduled</div></div><div class="crowd-placeholder"><b>Crowding unknown</b><small>No onboard occupancy data</small></div></div><div class="timeline-card"><div class="timeline-stops"><span>${escapeHtml(first?.from_stop?.stop_name||state.origin?.stop_name)}</span><span class="route-name">${escapeHtml(first?.route_name||first?.route_id||'')}</span><span style="text-align:right">${escapeHtml(last?.to_stop?.stop_name||state.destination?.stop_name)}</span></div><p class="subtle-note">${scheduleTime(journey.departure_datetime)} → ${scheduleTime(journey.arrival_datetime)} · scheduled, not live</p><p class="subtle-note">${escapeHtml(journey.legs?.length||0)} leg(s) · ${duration} min · source: ${escapeHtml(state.results?.data_source||'schedule service')}</p></div><button class="primary-action" data-action="open-journey" data-index="${index}">VIEW JOURNEY DETAILS <span class="material-symbols-outlined">arrow_forward</span></button></article>`
  }).join('')
  return `${pageHeader('Journey options')}<main class="screen"><div class="result-summary"><i class="summary-point"></i><span>${escapeHtml(state.origin?.stop_name||'Choose origin')}</span><span class="material-symbols-outlined summary-arrow">east</span><span>${escapeHtml(state.destination?.stop_name||'Choose destination')}</span><a href="#home" class="summary-edit" aria-label="Edit journey"><span class="material-symbols-outlined">edit</span></a></div><div class="filter-tabs">${[['balanced','Balanced'],['fastest','⚡ Fastest'],['comfort','♿ Comfort']].map(([v,l])=>`<button class="filter-tab ${state.preference===v?'active':''}" data-action="preference" data-value="${v}" ${state.journeyLoading?'disabled':''}>${l}</button>`).join('')}</div>${state.journeyLoading?'<div class="crowd-state">Loading the saved timetable and searching for scheduled trips…</div>':unavailable?`<div class="crowd-state"><strong>Journey planning unavailable</strong><br>${escapeHtml(state.results?.message||'A validated Delhi GTFS schedule is not currently connected. CrowdWise will show routes only when the backend confirms them.')}</div><button class="primary-action" data-action="retry-search">RETRY JOURNEY SEARCH</button>`:cards||'<div class="crowd-state">The schedule service returned no journeys for these stops and departure time.</div>'}</main>${bottomNav()}`
}
function journeyPage() {
  const journey=state.selectedJourney
  if(!journey) return `${pageHeader('Journey details')}<main class="screen"><div class="crowd-state">This journey is not available in the current session. Search again to choose a backend-confirmed scheduled journey.</div><button class="primary-action" data-route="home">BACK TO JOURNEY SEARCH</button></main>${bottomNav()}`
  const legs=journey.legs||[]
  const tools=`<button class="round-tool" data-action="save" aria-label="Save journey"><span class="material-symbols-outlined">bookmark</span></button><button class="round-tool" data-action="share" aria-label="Share journey"><span class="material-symbols-outlined">share</span></button>`
  const timeline=legs.map((leg,index)=>`<article class="journey-event"><span class="event-node"><span class="material-symbols-outlined">directions_bus</span></span><span class="event-label">${index?'Transfer · ':''}${escapeHtml(leg.route_name||leg.route_id)}</span><h3>${escapeHtml(leg.from_stop?.stop_name||'Boarding stop')}</h3><p>Scheduled departure: ${scheduleTime(leg.departure_datetime)}</p><div class="event-meta"><span>Alight at ${escapeHtml(leg.to_stop?.stop_name||'destination')}</span><span>Arrive ${scheduleTime(leg.arrival_datetime)}</span></div></article>`).join('')
  return `${pageHeader('Journey details','Scheduled itinerary',tools)}<main class="screen"><div class="demo-note" style="margin-top:15px"><span class="material-symbols-outlined">info</span><span>Schedule information only. It is not a live ETA; crowding and fares are not provided.</span></div><section class="detail-summary"><div class="route-badges"><span class="route-pill">${legs.length} ${legs.length===1?'leg':'legs'}</span><span class="tradeoff-pill">${Number(journey.transfers)||0} transfers</span></div><div class="place-list"><div class="place-stop">${escapeHtml(legs[0]?.from_stop?.stop_name||state.origin?.stop_name)}</div><div class="place-stop">${escapeHtml(legs.at(-1)?.to_stop?.stop_name||state.destination?.stop_name)}</div></div><div class="detail-stats"><div class="stat-box"><span>Scheduled duration</span><b>${Math.round((journey.duration_seconds||0)/60)}<small style="font-size:12px"> min</small></b></div><div class="stat-box"><span>Waiting</span><b>${Math.round((journey.waiting_seconds||0)/60)}<small style="font-size:12px"> min</small></b></div><div class="stat-box"><span>Fare</span><b style="font-size:13px">Not provided</b></div></div><p class="subtle-note">Source: ${escapeHtml(state.results?.data_source||'schedule service')} · generated ${scheduleTime(state.results?.generated_at)}</p></section><div class="timeline-title"><h2>Journey steps</h2><span class="sync-label">${escapeHtml(journey.eta_source||'SCHEDULED')}</span></div><section class="journey-timeline">${timeline||'<div class="crowd-state">No leg detail was returned by the schedule service.</div>'}</section><button class="report-route-btn" data-action="report-route"><span class="material-symbols-outlined">flag</span> Report crowding at a stop</button></main>${bottomNav()}`
}
function chartBars(observations=[]) {
  const hours=Array.from({length:24},(_,i)=>i), counts=hours.map(h=>observations.filter(o=>o.transaction_hour===h).reduce((sum,o)=>sum+(o.passenger_volume||0),0)), max=Math.max(1,...counts)
  return `<div class="bar-chart" role="img" aria-label="Historical ticket transaction volume by hour, 00:00 through 23:00">${counts.map(v=>`<span class="bar-wrap"><span class="bar" style="height:${Math.max(v?6:2,Math.round(v/max*100))}%"></span></span>`).join('')}</div><div class="bar-axis"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span></div>`
}
function stopPage() {
  const stopName=state.stop?.stop_name||state.origin?.stop_name||'Select a stop'
  const detail=state.stopData?.detail, demand=state.stopData?.demand, crowd=state.stopData?.crowd
  const isGtfsStop=Boolean(state.stop?.id&&!String(state.stop.id).startsWith('etm_'))
  const stopProvenance=isGtfsStop?'GTFS-listed location · not field-verified':'ETM stop label · no reviewed GTFS location match'
  const community=crowd?(crowd.status==='COMMUNITY_REPORTED'&&crowd.crowd_category?`<div class="crowd-state available"><strong>Community-reported: ${escapeHtml(crowd.crowd_category.replaceAll('_',' '))}</strong><br>${escapeHtml(crowd.report_count)} recent reports · subjective rider reports, not a measured passenger count.</div>`:`<div class="crowd-state">No report summary is available yet. This does not mean the stop is uncrowded.</div>`):state.stopLoading?'<div class="crowd-state">Checking recent voluntary reports…</div>':'<div class="crowd-state">The community crowd summary could not be loaded.</div><button class="text-link" data-action="retry-stop">Retry</button>'
  const reportList=state.stopData?.reports?.reports||[]
  const recentReports=reportList.length?`<div class="data-card"><strong>Recent individual reports</strong>${reportList.map(report=>`<p class="event-meta"><b>${escapeHtml(String(report.category).replaceAll('_',' '))}</b><span>${escapeHtml(report.observed_at)}</span></p>`).join('')}<p class="subtle-note">Voluntary reports; not a passenger count. Reports expire automatically.</p></div>`:''
  const bars=demand?.observations?.length?chartBars(demand.observations):'<div class="crowd-state">Historical activity is unavailable for this stop right now.</div>'
  const coverage=detail?.first_observed_date&&detail?.last_observed_date?`${detail.first_observed_date} to ${detail.last_observed_date}`:'October 2026 dataset window'
  const demandUnavailable=state.stopData?.demandError?.status===409?'This GTFS stop has no reviewed link to the historical ETM ticket records. The schedule and location can be used; historical activity is unavailable here.':'Historical ticket activity could not be loaded for this stop.'
  return `${pageHeader('Stop details')}<main class="screen">${state.stopError?`<div class="crowd-state">${escapeHtml(state.stopError)} <button data-action="retry-stop">Retry</button></div>`:''}<div class="stop-banner"><span class="soft-tag">● &nbsp;Bus stop</span><span class="soft-tag orange">${escapeHtml(stopProvenance)}</span></div><h1 class="stop-name">${escapeHtml(detail?.stop_name||stopName)}</h1><div class="stop-subtitle">${detail?.coordinates?'GTFS coordinates available · not independently field-verified':'Coordinates not available'} · ${isGtfsStop?'static GTFS':'ETM'} source</div>
    <div class="insight-card"><span class="insight-icon"><span class="material-symbols-outlined">query_stats</span></span><div><h3>Historical ticket activity</h3><p>October 2026 ticket records describe past transaction activity. They do not measure today's queue, bus occupancy, or crowding.</p></div></div>
     <section class="data-card"><div class="demand-head"><div class="demand-title"><span class="material-symbols-outlined" style="color:#98421b">history</span>Historical demand activity</div><span class="segmented"><span>HOURLY</span></span></div>${demand?`<div class="metric-number">${Number(demand.passenger_volume).toLocaleString('en-IN')}</div><div class="metric-caption">ticketed passenger-volume records · ${escapeHtml(demand.days_covered)} days</div>${bars}${demand.observations_truncated?'<p class="subtle-note">Chart shows a limited sample of observations.</p>':''}<div class="window-note">${escapeHtml(coverage)} · ${escapeHtml(demand.data_source)}</div><p class="subtle-note">Historical ticket rows, not confirmed boardings or a crowd estimate. ${escapeHtml(demand.timestamp_basis)}</p>`:state.stopLoading?'<div class="skeleton" style="margin-top:18px"></div>':`<div class="crowd-state">${escapeHtml(demandUnavailable)}</div>`}</section>
     <div class="section-head"><h2>Reported at this stop</h2><span class="kicker">COMMUNITY SIGNAL</span></div>${community}${recentReports}<div class="section-head"><h2>Journey planning</h2><span class="kicker">${state.capabilities?.scheduled_journey_search?'STATIC SCHEDULE':'SCHEDULE UNAVAILABLE'}</span></div><div class="crowd-state">${state.capabilities?.scheduled_journey_search?'This stop is in the static GTFS schedule. Choose it as your origin to compare scheduled journeys; arrival times are approximate, not live.':'No validated static timetable is connected, so scheduled journeys are unavailable.'}</div>${state.capabilities?.scheduled_journey_search?'<button class="primary-action" data-action="plan-from-stop">PLAN FROM THIS STOP</button>':''}<button class="report-choice-link" data-action="report-stop"><span class="material-symbols-outlined" style="vertical-align:middle">flag</span> &nbsp;Share a crowd observation</button>
    <label class="form-label">LOOK UP ANOTHER STOP</label><span class="stop-autocomplete" data-autocomplete="stop"><input data-stop-field="stop" value="${escapeHtml(stopName)}" placeholder="Search stop names" autocomplete="off"><span class="suggestions" data-suggestions="stop" hidden></span></span></main>${bottomNav()}`
}
const crowdChoices=[['low','sentiment_satisfied','Quiet','Feels lightly crowded','Low'],['moderate','groups','Some crowd','A noticeable crowd is present','Moderate'],['high','groups','Crowded','Busy around the stop','High'],['very_high','pan_tool','Very crowded','Very busy; boarding may be difficult','Very high']]
const feedbackChoices=[['bus_arriving','Bus arriving','directions_bus'],['long_wait','Long wait','schedule'],['service_disruption','Service disruption','warning'],['other','Other','more_horiz']]
function reportPage() {
  if(state.reportSent) return `${pageHeader('Update shared')}<main class="screen"><div class="saved-empty"><span class="material-symbols-outlined">check_circle</span><h2>Thanks for helping riders</h2><p>Your report was sent as a voluntary community observation. It is not a measured passenger count and will expire automatically.</p><button class="primary-action" data-route="home">BACK TO HOME</button></div></main>${bottomNav()}`
  const stop=state.reportStop
  const locationNote=stop?.coordinates?'The stop location is listed in GTFS and has not been independently checked in the field.':'The selected stop name does not have a reviewed physical-location match.'
  return `${pageHeader('Crowd reporting')}<main class="screen"><div class="report-corridor"><i></i><span>${escapeHtml(state.reportRoute||'BUS STOP')}</span><span>·</span><span>${escapeHtml(stop?.stop_name||'Choose a stop below')}</span></div><h1 class="report-title">How crowded does it feel right now?</h1><p class="report-intro">Your quick, voluntary report helps riders understand what other people are experiencing.</p><label class="form-label">STOP NAME</label><span class="stop-autocomplete" data-autocomplete="report"><input data-stop-field="report" value="${escapeHtml(stop?.stop_name||'')}" placeholder="Search and select a bus stop" autocomplete="off"><span class="suggestions" data-suggestions="report" hidden></span></span>
    <div class="crowd-options">${crowdChoices.map(([id,icon,title,description,level])=>`<button class="crowd-option ${state.reportCategory===id?'selected':''}" data-action="crowd-category" data-value="${id}"><span class="crowd-option-icon"><span class="material-symbols-outlined">${icon}</span></span><span class="crowd-option-copy"><strong>${title}<span class="crowd-level">${level}</span></strong><small>${description}</small></span><span class="radio-mark"></span></button>`).join('')}</div>
    <div class="section-head"><h2 style="font-size:17px">Quick impressions</h2><span class="kicker">OPTIONAL</span></div><div class="quick-tags">${feedbackChoices.map(([id,label,icon])=>`<button class="quick-tag ${state.reportFeedback===id?'selected':''}" data-action="feedback" data-value="${id}"><span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle">${icon}</span> ${label}</button>`).join('')}</div>
    <div class="demo-note"><span class="material-symbols-outlined">info</span><span>This is a voluntary report, not a passenger count. ${escapeHtml(locationNote)} Reports expire automatically.</span></div><button class="report-submit" data-action="submit-report" ${!state.reportCategory||!stop?.id?'disabled':''}>SHARE UPDATE WITH COMMUTERS <span class="material-symbols-outlined">arrow_forward</span></button><p class="privacy-caption">Community report · not a headcount</p></main>${bottomNav()}`
}
function ridesPage() {
  let saved
  try { saved=JSON.parse(localStorage.getItem(savedKey)||'[]'); if(!Array.isArray(saved)) saved=[];saved=saved.filter(item=>item?.originId&&item?.destinationId&&Array.isArray(item.legs)&&item.legs.length>0);localStorage.setItem(savedKey,JSON.stringify(saved)) } catch { saved=[] }
  return `${pageHeader('Your rides')}<main class="screen">${saved.length?saved.map((item,i)=>`<article class="saved-item"><span class="kicker">SAVED SCHEDULED JOURNEY · THIS DEVICE</span><h2>${escapeHtml(item.origin)} <span style="color:#98421b">→</span> ${escapeHtml(item.destination)}</h2><p class="subtle-note">${escapeHtml(item.legs?.map(leg=>leg.route_name||leg.route_id).join(' · ')||'Scheduled itinerary')} · saved locally; not synced</p><button class="text-link" data-action="restore-ride" data-index="${i}">Open details →</button><button class="text-link" data-action="remove-ride" data-index="${i}">Remove</button></article>`).join(''):`<div class="saved-empty"><span class="material-symbols-outlined">all_inclusive</span><h2>No saved journeys yet</h2><p>Only journeys confirmed by the schedule service can be saved.</p><button class="primary-action" data-route="home">PLAN A JOURNEY</button></div>`}</main>${bottomNav()}`
}
function authPage() {
  return `${pageHeader('Account')}<main class="screen"><div class="crowd-state"><strong>Accounts are not available yet.</strong><br>CrowdWise has no authentication service connected. No credentials are collected or accepted. You can use stop insights and community reporting without signing in.</div><button class="primary-action" data-route="home">CONTINUE WITHOUT AN ACCOUNT</button></main>${bottomNav()}`
}
function operatorBars(data){
  const items=data?.points||data?.items||data?.trends||[]
  if(!items.length)return '<div class="crowd-state">No chart data is available from the current analytics response.</div>'
  const values=items.slice(-14).map(x=>Number(x.passenger_volume||x.transaction_count||x.value||0)),max=Math.max(1,...values)
  return `<div class="bar-chart">${values.map(v=>`<span class="bar-wrap"><span class="bar" style="height:${Math.max(3,Math.round(v/max*100))}%"></span></span>`).join('')}</div><p class="subtle-note">Recorded historical ticket values only.</p>`
}
function operatorPage() {
  if(!state.operatorData){state.operatorData={loading:true};loadOperator()}
  const d=state.operatorData
  const first=d.overview?.dataset_min_timestamp?new Date(d.overview.dataset_min_timestamp):null,last=d.overview?.dataset_max_timestamp?new Date(d.overview.dataset_max_timestamp):null
  const days=first&&last?Math.floor((last-first)/86400000)+1:'—',routes=d.corridors?.routes||d.corridors?.items||[]
  return `${pageHeader('Operator insights','PHASE 2 · HISTORICAL ONLY')}<main class="screen"><div class="demo-note" style="margin-top:14px"><span class="material-symbols-outlined">info</span><span>Historical ticket activity only. This is not passenger occupancy, live crowding, or vehicle telemetry.</span></div>${d.loading?'<div class="data-card"><div class="skeleton" style="width:70%"></div><div class="skeleton" style="width:90%;margin-top:16px"></div></div>':d.error?`<div class="crowd-state">Analytics are unavailable: ${escapeHtml(d.error)}</div><button class="primary-action" data-action="retry-operator">RETRY ANALYTICS</button>`:`<div class="data-card"><span class="kicker">SOURCE DATASET</span><h2>Ticket activity overview</h2><p>${escapeHtml(d.overview?.data_source||'Historical ETM dataset')} · historical records</p><div class="detail-stats"><div class="stat-box"><span>Ticket rows</span><b>${escapeHtml(d.overview?.dataset_rows?.toLocaleString?.('en-IN')||'—')}</b></div><div class="stat-box"><span>Days covered</span><b>${escapeHtml(days)}</b></div><div class="stat-box"><span>Route labels</span><b>${escapeHtml(d.overview?.distinct_routes?.toLocaleString?.('en-IN')||'—')}</b></div></div></div><div class="data-card"><div class="demand-title">Recorded ticket activity</div>${operatorBars(d.trends)}</div><div class="data-card"><div class="demand-title">Historical route labels</div>${routes.slice(0,6).map(c=>`<p class="event-meta"><b>${escapeHtml(c.route_label||c.route||'Route')}</b><span>${escapeHtml(c.passenger_volume??c.transaction_count??'—')} recorded</span></p>`).join('')}</div>`}</main>${bottomNav()}`
}
function render() {
  const nextPage=location.hash.slice(1)||'home'
  if(state.map){state.map.remove();state.map=null}
  if(nextPage!=='live'&&state.liveTimer){clearInterval(state.liveTimer);state.liveTimer=null}
  if(nextPage==='report'&&state.page!=='report'){state.reportStop=state.stop||state.origin;state.reportCategory=null;state.reportSent=false}
  state.page=nextPage
  const pages={home:homePage,results:resultsPage,journey:journeyPage,live:liveMapPage,stop:stopPage,report:reportPage,rides:ridesPage,auth:authPage,operator:operatorPage}
  app.innerHTML=(pages[state.page]||homePage)()
  if(state.page==='live'){
    drawLiveMap()
    if(!state.liveTimer)state.liveTimer=setInterval(()=>{if(state.page==='live')loadLiveData()},60000)
    if(!state.liveLoaded&&!state.liveLoading)loadLiveData()
  }
  if(state.page==='stop'&&(state.stop||state.origin)?.id&&!state.stopData&&!state.stopLoading){state.stop=state.stop||state.origin;loadStopData(state.stop)}
}
async function loadDefaults(){
  try{
    state.capabilities=await api.capabilities()
    state.capabilityError=null
    render()
  }catch(error){state.capabilities=null;state.capabilityError=error.message;console.warn('Capability lookup unavailable',error);render()}
}
async function loadStopData(stop){
  state.stopLoading=true;state.stopData=null;state.stopError=null;render()
  const [detail,demand,crowd,reports]=await Promise.allSettled([api.stop(stop.id),api.demand(stop.id),api.crowdAtStop(stop.id),api.reportsAtStop(stop.id)])
  state.stopData={detail:detail.status==='fulfilled'?detail.value:null,demand:demand.status==='fulfilled'?demand.value:null,demandError:demand.status==='rejected'?demand.reason:null,crowd:crowd.status==='fulfilled'?crowd.value:null,reports:reports.status==='fulfilled'?reports.value:null}
  if(detail.status==='rejected'&&demand.status==='rejected'&&crowd.status==='rejected'&&reports.status==='rejected')state.stopError='Stop information could not be loaded. Check your connection and retry.'
  state.stopLoading=false
  if(state.page==='stop')render()
}
async function resolveStop(field){
  const input=document.querySelector(`[data-stop-field="${field}"]`), query=input?.value?.trim()||''
  const current=field==='origin'?state.origin:field==='destination'?state.destination:field==='stop'?state.stop:state.reportStop
  if(current?.id&&current.stop_name.toLowerCase()===query.toLowerCase())return current
  const matches=await api.searchStops(query,10)
  if(input&&input.value.trim()!==query)return null
  const match=matches.find(s=>s.stop_name.toLowerCase()===query.toLowerCase())
  if(match)return match
  const box=document.querySelector(`[data-suggestions="${field}"]`)
  if(box){box.innerHTML=matches.length?matches.map(s=>suggestionHtml(s,field)).join(''):'<div class="suggestion">No matching stop. Try another name.</div>';box.hidden=false}
  return null
}
async function useCurrentLocation(){
  if(!navigator.geolocation){toast('This browser does not provide location. Search for a stop by name.');return}
  state.locationLoading=true;render()
  navigator.geolocation.getCurrentPosition(async position=>{
    try{
      const result=await api.nearbyStop(position.coords.latitude,position.coords.longitude)
      const nearest=result.items?.[0]
      if(!nearest){toast('No validated bus stop was found within 25 km. Search by stop name instead.');return}
      state.origin={id:nearest.id,stop_name:nearest.stop_name,coordinates:nearest.coordinates}
      toast(`Origin set to ${nearest.stop_name} · ${nearest.distance_meters} m away`)
    }catch(error){toast(error.status===503?'Nearest-stop lookup needs a validated static GTFS dataset. Search by stop name instead.':`Could not find a nearby stop: ${error.message}`)}
    finally{state.locationLoading=false;render()}
  },error=>{
    state.locationLoading=false;render()
    const message=error.code===error.PERMISSION_DENIED?'Location permission was denied. You can search for a stop by name.':error.code===error.TIMEOUT?'Location lookup timed out. Try again or search by stop name.':'Your location is unavailable. Search for a stop by name.'
    toast(message)
  },{enableHighAccuracy:false,timeout:10000,maximumAge:0})
}
function suggestionHtml(stop,field){const coordinates=stop.coordinates&&Number.isFinite(Number(stop.coordinates.latitude))&&Number.isFinite(Number(stop.coordinates.longitude))?`${Number(stop.coordinates.latitude).toFixed(5)}, ${Number(stop.coordinates.longitude).toFixed(5)} · GTFS coordinates`:`Stop ID ${escapeHtml(stop.id)} · location not verified`;return `<button type="button" class="suggestion" aria-label="${escapeHtml(stop.stop_name)}" data-action="choose-stop" data-field="${field}" data-stop-id="${escapeHtml(stop.id)}" data-stop-name="${escapeHtml(stop.stop_name)}"><span>${escapeHtml(stop.stop_name)}</span><small>${coordinates}</small></button>`}
async function showSuggestions(field,query){
  const box=document.querySelector(`[data-suggestions="${field}"]`)
  if(!box)return
  if(query.trim().length<2){box.hidden=true;return}
  const input=document.querySelector(`[data-stop-field="${field}"]`),version=(input._searchVersion||0)+1;input._searchVersion=version
  box.innerHTML='<div class="suggestion">Searching stops…</div>';box.hidden=false
  try{const items=await api.searchStops(query,8);if(input._searchVersion!==version)return;box.innerHTML=items.length?items.map(s=>suggestionHtml(s,field)).join(''):'<div class="suggestion">No matching stops found.</div>'}catch{if(input._searchVersion===version)box.innerHTML='<div class="suggestion">Stop search is unavailable. Check the backend connection.</div>'}
}
async function journeySearch(){
  const button=document.querySelector('[data-action="search"]');if(button)button.disabled=true
  try{
    const [origin,destination]=await Promise.all([resolveStop('origin'),resolveStop('destination')])
    if(!origin||!destination){toast('Choose both stops from the suggestion list.');return}
    if(origin.id===destination.id){toast('Choose two different stops.');return}
    state.origin=origin;state.destination=destination;state.results=null;state.journeyLoading=false
    if(!state.capabilities&&!state.capabilityError)try{state.capabilities=await api.capabilities()}catch(error){state.capabilityError=error.message}
    const dateField=document.querySelector('[data-departure]')
    if(dateField?.value)state.departure=new Date(dateField.value)
    if(Number.isNaN(state.departure.getTime())||state.departure<new Date(Date.now()-60000)){toast('Choose a valid departure time in the future.');return}
    if(state.capabilityError)state.results={data_status:'unavailable',message:`Backend status unavailable: ${state.capabilityError}`}
    else if(state.capabilities?.scheduled_journey_search){try{state.results=await api.journeySearch({origin_stop_id:origin.id,destination_stop_id:destination.id,departure_datetime:state.departure.toISOString(),preference:state.preference,max_transfers:1})}catch(error){state.results={data_status:'unavailable',message:error.message};toast(`Journey search failed: ${error.message}`)}}else state.results={data_status:'unavailable',message:'A validated Delhi GTFS timetable is not currently connected.'}
    location.hash='#results'
  }catch(error){state.results={data_status:'unavailable',message:`Stop search failed: ${error.message}`};toast(`Stop search failed: ${error.message}`);location.hash='#results'}
  finally{if(button)button.disabled=false}
}
function selectStop(field,stop){
  if(field==='origin')state.origin=stop
  else if(field==='destination')state.destination=stop
  else if(field==='stop'){state.stop=stop;state.stopData=null;loadStopData(stop)}
  else if(field==='report'){state.reportStop=stop;state.stop=stop;state.reportSent=false}
  const input=document.querySelector(`[data-stop-field="${field}"]`);if(input)input.value=stop.stop_name
  if(input)input._searchVersion=(input._searchVersion||0)+1
  const box=document.querySelector(`[data-suggestions="${field}"]`);if(box)box.hidden=true
  if(field==='report')render()
}
function getReportToken(){
  const makeToken=()=>globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`
  try{let token=localStorage.getItem(tokenKey);if(!token){token=makeToken();localStorage.setItem(tokenKey,token)}return token}
  catch{return state.reportClientToken||(state.reportClientToken=makeToken())}
}
async function submitReport(){
  const stop=state.reportStop
  if(!stop?.id){toast('Select a stop from the list before sharing.');return}
  if(!state.reportCategory){toast('Choose how crowded it feels first.');return}
  const btn=document.querySelector('[data-action="submit-report"]');if(btn){btn.disabled=true;btn.textContent='SENDING…'}
  try{
    const result=await api.submitReport({stop_id:stop.id,category:state.reportCategory,observed_at:new Date().toISOString(),route_id:state.reportRoute||null,feedback_code:state.reportFeedback},getReportToken())
    state.reportSent=true;render();toast(`Report recorded · expires ${new Date(result.expires_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`)
  }catch(error){if(error.status===409)toast('A recent report from this app is already active for this stop.');else if(error.status===429)toast('Report limit reached. Please try again later.');else toast(`Report not sent: ${error.message}`);if(btn)btn.disabled=false}
}
async function openStop(){const stop=state.stop||state.origin;if(!stop?.id){toast('Select a stop from search first.');location.hash='#home';return}state.stop=stop;state.stopData=null;location.hash='#stop'}
function saveJourney(){
  if(!state.selectedJourney||!state.origin?.id||!state.destination?.id){toast('Only a backend-confirmed journey can be saved.');return}
  try{const stored=JSON.parse(localStorage.getItem(savedKey)||'[]');if(!Array.isArray(stored))throw new Error();const list=stored.filter(item=>item?.originId&&item?.destinationId&&Array.isArray(item.legs)&&item.legs.length>0);const item={origin:state.origin.stop_name,originId:state.origin.id,destination:state.destination.stop_name,destinationId:state.destination.id,legs:state.selectedJourney.legs||[],duration_seconds:state.selectedJourney.duration_seconds,transfers:state.selectedJourney.transfers,waiting_seconds:state.selectedJourney.waiting_seconds,eta_source:state.selectedJourney.eta_source,createdAt:new Date().toISOString()};localStorage.setItem(savedKey,JSON.stringify([item,...list].slice(0,10)));toast('Journey saved on this device. It will not sync across devices.')}catch{toast('Could not save this journey in browser storage.')}
}
async function clickHandler(event){
  const node=event.target.closest('[data-action],[data-route]');if(!node)return
  if(node.dataset.route){location.hash=`#${node.dataset.route}`;return}
  const {action,value,field,stopId,stopName}=node.dataset
  if(action==='back'){location.hash=state.page==='journey'?'#results':state.page==='results'?'#home':'#home'}
  if(action==='swap'){const old=state.origin;state.origin=state.destination;state.destination=old;render()}
  if(action==='preference'){
    state.preference=value
    if(state.page==='results'&&state.capabilities?.scheduled_journey_search&&state.origin?.id&&state.destination?.id){
      state.journeyLoading=true;state.results=null;render()
      try{state.results=await api.journeySearch({origin_stop_id:state.origin.id,destination_stop_id:state.destination.id,departure_datetime:state.departure.toISOString(),preference:value,max_transfers:1})}
      catch(error){state.results={data_status:'unavailable',message:error.message}}
      finally{state.journeyLoading=false;render()}
    }else render()
  }
  if(action==='search')await journeySearch()
  if(action==='retry-search')await journeySearch()
  if(action==='retry-capabilities'){state.capabilityError=null;await loadDefaults()}
  if(action==='choose-stop')selectStop(field,{id:stopId,stop_name:stopName})
  if(action==='open-journey'){state.selectedJourney=state.results?.options?.[Number(node.dataset.index)]||null;if(state.selectedJourney)location.hash='#journey';else toast('This itinerary is not available. Search again.')}
  if(action==='open-stop')await openStop()
  if(action==='plan-from-stop'&&state.stop){state.origin=state.stop;state.destination=null;location.hash='#home'}
  if(action==='report-route'){state.stop=state.origin;state.reportStop=state.origin;state.reportRoute=state.selectedJourney?.legs?.[0]?.route_id||null;state.reportCategory=null;state.reportFeedback=null;state.reportSent=false;location.hash='#report'}
  if(action==='report-stop'){state.reportStop=state.stop||state.origin;state.reportRoute=null;state.reportCategory=null;state.reportFeedback=null;state.reportSent=false;location.hash='#report'}
  if(action==='crowd-category'){state.reportCategory=value;render()}
  if(action==='feedback'){state.reportFeedback=state.reportFeedback===value?null:value;render()}
  if(action==='submit-report')await submitReport()
  if(action==='save')saveJourney()
  if(action==='share'){if(!state.selectedJourney){toast('There is no confirmed journey to share.');return}const text=`CrowdWise scheduled journey: ${state.origin?.stop_name} to ${state.destination?.stop_name}`;try{if(navigator.share)await navigator.share({title:'CrowdWise scheduled journey',text});else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);toast('Journey summary copied.')}else toast('Sharing is not supported by this browser.')}catch(error){if(error.name!=='AbortError')toast('Could not share this journey.')}}
  if(action==='restore-ride'){try{const item=JSON.parse(localStorage.getItem(savedKey)||'[]')[Number(node.dataset.index)];if(item?.originId&&item?.destinationId&&Array.isArray(item.legs)&&item.legs.length){state.selectedJourney=item;state.origin={id:item.originId,stop_name:item.origin};state.destination={id:item.destinationId,stop_name:item.destination};location.hash='#journey'}else toast('This saved item has no confirmed schedule details. Remove it and plan again.')}catch{toast('Saved journeys could not be read from browser storage.')}}
  if(action==='remove-ride'){try{const list=JSON.parse(localStorage.getItem(savedKey)||'[]');list.splice(Number(node.dataset.index),1);localStorage.setItem(savedKey,JSON.stringify(list));render()}catch{toast('Could not update browser storage.')}}
  if(action==='retry-stop'&&state.stop)loadStopData(state.stop)
  if(action==='retry-operator'){state.operatorData={loading:true};render();loadOperator()}
  if(action==='retry-live')await loadLiveData()
  if(action==='current-location')await useCurrentLocation()
}
app.addEventListener('click',clickHandler)
app.addEventListener('input',event=>{
  const input=event.target.closest('[data-stop-field]');if(!input)return
  const field=input.dataset.stopField
  input._searchVersion=(input._searchVersion||0)+1
  const selected=field==='origin'?state.origin:field==='destination'?state.destination:field==='stop'?state.stop:state.stop
  if(selected&&selected.stop_name.toLowerCase()!==input.value.trim().toLowerCase()){
    if(field==='origin')state.origin=null
    else if(field==='destination')state.destination=null
    else if(field==='stop')state.stop=null
    else if(field==='report'){state.reportStop=null;state.stop=null}
  }
  clearTimeout(input._searchTimer);input._searchTimer=setTimeout(()=>showSuggestions(field,input.value),180)
})
app.addEventListener('focusin',event=>{const input=event.target.closest('[data-stop-field]');if(input&&input.value.trim().length>1)showSuggestions(input.dataset.stopField,input.value)})
app.addEventListener('submit',event=>{if(event.target.id==='auth-form')event.preventDefault()})
window.addEventListener('hashchange',render)
async function loadOperator(){
  try{const [overview,trends,corridors]=await Promise.all([api.overview(),api.trends(),api.corridors()]);state.operatorData={overview,trends,corridors};if(state.page==='operator')render()}
  catch(error){state.operatorData={error:error.message};if(state.page==='operator')render()}
}
render()
loadDefaults()


