import { api } from './api.js?v=journey-controls-3'

const app = document.querySelector('#app')
const toastNode = document.querySelector('#toast')
const savedKey = 'yuktix.savedJourneys.v1'
const tokenKey = 'yuktix.reportClient.v1'
const state = { page: location.hash.slice(1) || 'home', origin: null, destination: null, stop: null, reportStop: null, reportRoute: null, preference: 'balanced', departure: new Date(Date.now() + 5 * 60000), reportCategory: null, reportFeedback: null, capabilities: null, capabilityError: null, results: null, selectedJourney: null, stopData: null, stopLoading: false, reportSent: false, operatorData: null, stopError: null, routeQuery: '', routeMatches: [], selectedRoute: null, routeStops: [], routeLoading: false, routeOriginId: '', routeDestinationId: '', crowdMode: 'bus', crowdRouteQuery: '', crowdRouteMatches: [], crowdRoute: null, crowdActivity: [], crowdActivityLoading: false, crowdActivityError: null }
const ticketActivityCache = new Map()
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[char])
let toastTimer
function toast(message) { toastNode.textContent = message; toastNode.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toastNode.classList.remove('show'), 3200) }
function pageHeader(title, subtitle = '', tools = '') { return `<header class="page-head"><button class="back-btn" data-action="back" aria-label="Back"><span class="material-symbols-outlined">arrow_back</span></button><div class="page-title">${escapeHtml(title)}${subtitle ? `<span class="page-subtitle">${escapeHtml(subtitle)}</span>` : ''}</div><div class="page-tools">${tools}</div></header>` }
function scheduleTime(value) { if(!value)return 'Not provided';const date=new Date(value);return escapeHtml(Number.isNaN(date.getTime())?value:date.toLocaleString([], {dateStyle:'medium',timeStyle:'short'})) }
function fareCompactText(fare) {
  if(fare?.status==='estimated')return `₹${fare.ordinary_adult_total_inr} / ₹${fare.ac_adult_total_inr}`
  if(fare?.status==='partial')return 'Partial'
  return 'Unavailable'
}
function brandHeader(label = 'Home Search') { return `<header class="topbar"><a class="brand" href="#home"><span class="brand-mark"><span class="material-symbols-outlined">hub</span></span><span><b>YUKTIX</b><small>${escapeHtml(label)}</small></span></a><div class="header-actions"><button class="icon-btn" data-route="operator" aria-label="Historical ticket insights"><span class="material-symbols-outlined">insights</span></button><button class="avatar" data-route="auth" aria-label="Account options"><span class="material-symbols-outlined">person</span></button></div></header>` }
function journeyElapsedSeconds(journey){const arrival=Date.parse(journey.arrival_datetime);const departure=state.departure.getTime();return Number.isFinite(arrival)?Math.max(0,(arrival-departure)/1000):Number(journey.duration_seconds||0)}
function orderedJourneyOptions(){
  const options=[...(state.results?.options||[])],maxElapsed=Math.max(1,...options.map(journeyElapsedSeconds)),maxTransfers=Math.max(1,...options.map(item=>Number(item.transfers)||0))
  const balanced=item=>.5*(journeyElapsedSeconds(item)/maxElapsed)+.5*((Number(item.transfers)||0)/maxTransfers)
  return options.sort((a,b)=>{
    if(state.preference==='fastest')return journeyElapsedSeconds(a)-journeyElapsedSeconds(b)||(Number(a.transfers)||0)-(Number(b.transfers)||0)
    if(state.preference==='comfort'){
      const aa=a.ticketActivity?.complete?Number(a.ticketActivity.averagePassengers):null,bb=b.ticketActivity?.complete?Number(b.ticketActivity.averagePassengers):null
      if(aa!==null&&bb!==null&&aa!==bb)return aa-bb
      if((aa===null)!==(bb===null))return aa===null?1:-1
    }
    return balanced(a)-balanced(b)||journeyElapsedSeconds(a)-journeyElapsedSeconds(b)
  })
}
async function loadJourneyTicketActivity(options){
  const legs=options.flatMap((option,index)=>(option.legs||[]).map(leg=>({option,index,leg})))
  const unique=new Map()
  for(const {leg} of legs){if(!leg.route_id||!leg.departure_datetime)continue;const key=`${leg.route_id}|${String(leg.departure_datetime).slice(0,13)}`;if(!unique.has(key)){if(!ticketActivityCache.has(key))ticketActivityCache.set(key,api.routeActivity(leg.route_id,leg.departure_datetime).catch(()=>null));unique.set(key,ticketActivityCache.get(key))}}
  await Promise.all(unique.values())
  for(const option of options){
    const activities=(option.legs||[]).map(leg=>{const key=`${leg.route_id}|${String(leg.departure_datetime||'').slice(0,13)}`;return unique.has(key)?ticketActivityCache.get(key):null})
    const values=await Promise.all(activities)
    const passengers=values.map(item=>item?.status==='available'?Number(item.average_passenger_volume):null)
    option.ticketActivity={complete:passengers.length>0&&passengers.every(Number.isFinite),averagePassengers:passengers.every(Number.isFinite)?passengers.reduce((sum,value)=>sum+value,0):null,matchedLegs:passengers.filter(Number.isFinite).length,totalLegs:passengers.length}
  }
  if(state.page==='results')render()
}
function bottomNav() {
  const active = state.page === 'home' ? 'home' : ['results','journey','rides'].includes(state.page) ? 'rides' : state.page === 'stop' ? state.crowdMode : ''
  return `<nav class="bottom-nav" aria-label="Main navigation"><a class="${active==='home'?'selected':''}" href="#home"><span class="material-symbols-outlined">search</span>Search</a><a class="${active==='rides'?'selected':''}" href="#rides"><span class="material-symbols-outlined">alt_route</span>Routes</a><a class="${active==='stop'?'selected':''}" href="#stop" data-action="crowd-mode" data-value="stop"><span class="material-symbols-outlined">location_on</span>Stops</a><a class="${active==='bus'?'selected':''}" href="#stop" data-action="crowd-mode" data-value="bus"><span class="material-symbols-outlined">groups</span>Crowd</a></nav>`
}
function autocomplete(field, label, value) {
  return `<label class="location-row ${field}-row"><span class="location-dot ${field==='origin'?'origin-dot':'destination-dot'}"></span><span class="field-copy"><span class="field-label">${label}</span><span class="stop-autocomplete" data-autocomplete="${field}"><input data-stop-field="${field}" value="${escapeHtml(value)}" placeholder="" autocomplete="off" aria-label="${label}"><span class="suggestions" data-suggestions="${field}" hidden></span></span></span></label>`
}
function homePage() {
  const originName = state.origin?.stop_name || ''
  const destinationName = state.destination?.stop_name || ''
  const routeOptions = field => state.routeStops.map(stop => `<option value="${escapeHtml(stop.stop_id)}" ${stop.stop_id===(field==='origin'?state.routeOriginId:state.routeDestinationId)?'selected':''}>${escapeHtml(stop.stop_name)}</option>`).join('')
  const routePanel = state.selectedRoute ? `<section class="selected-route-panel"><div class="selected-route-heading"><span class="route-icon material-symbols-outlined">directions_bus</span><span><b>Route ${escapeHtml(state.selectedRoute.route_name)}</b><small>${escapeHtml(state.selectedRoute.headsign || state.selectedRoute.route_long_name || 'GTFS scheduled route')}</small></span><button class="route-clear" type="button" data-action="clear-route" aria-label="Clear selected route">×</button></div>${state.routeLoading ? '<p class="route-loading">Loading scheduled stops…</p>' : state.routeStops.length ? `<label class="route-stop-label">BOARD AT<select data-route-stop="origin">${routeOptions('origin')}</select></label><label class="route-stop-label">GET OFF AT<select data-route-stop="destination">${routeOptions('destination')}</select></label><small class="route-pattern-note">${escapeHtml(state.selectedRoute.pattern_note || 'Stops shown from the static GTFS schedule.')}</small>` : '<p class="route-loading">Could not load the stops for this route.</p>'}</section>` : ''
  return `${brandHeader('Home Search')}<main class="screen"><section class="hero hero-stitch"><div class="hero-copy"><span class="grid-pill"><i></i>Delhi bus journey planner</span><h1>Plan your<br><em>smart journey</em></h1><p>Find scheduled bus routes, compare travel times and view estimated fares.</p></div><div class="hero-art"><img src="https://lh3.googleusercontent.com/aida-public/AB6AXuBXKSKAja9l5zwO4pkmFSytWQcCl_rUAAVgLnzxanjiQS54YYGuShGvFt2y6rM0-F885zXOVfjz3EhV6APeQ1n6BKEEVnBMKhnsRH4hKksNuAPcNUTCZqq7lnzheAUASzfDJgNdlCdb85NSYO_JUiAEjIVdI7VJN7JStsHzjV--dByVapotcCmyknOp8c0Mzv7bNN7h41789p4m7_hlsljynPTkuKdPTiOQllf1NKa03lQ0a_Ze4NLg" alt="Delhi transit bus and monument"></div></section>
    <section class="search-card" aria-label="Plan your journey">${autocomplete('origin','ORIGIN POINT',originName)}
      <div class="swap-line"><span></span><button class="swap" data-action="swap" aria-label="Swap origin and destination"><span class="material-symbols-outlined">swap_vert</span></button></div>
      ${autocomplete('destination','DESTINATION',destinationName)}
      <div class="options"><label class="time-chip"><span class="material-symbols-outlined">schedule</span><span>Depart</span><input data-departure type="datetime-local" value="${new Date(state.departure.getTime()-state.departure.getTimezoneOffset()*60000).toISOString().slice(0,16)}" aria-label="Departure date and time"></label></div>
      <div class="route-search"><div class="route-divider"><span></span>OR SEARCH BY ROUTE<span></span></div><div class="route-search-input"><span class="material-symbols-outlined">directions_bus</span><input data-route-query value="${escapeHtml(state.routeQuery)}" placeholder="Bus number (e.g. 534, 102A)" autocomplete="off" aria-label="Search bus route"><button type="button" data-action="route-search" aria-label="Search route"><span class="material-symbols-outlined">arrow_forward</span></button><div class="route-suggestions" data-route-suggestions hidden></div></div>${routePanel}</div>
    </section><button class="cta" data-action="search"><span class="cta-label"><span class="material-symbols-outlined">search</span>${state.selectedRoute?'FIND JOURNEYS ON ROUTE':'FIND SMART JOURNEY'}</span><span class="cta-arrow"><span class="material-symbols-outlined">arrow_forward</span></span></button>
    </main>${bottomNav()}`
}
function resultsPage() {
  const options=orderedJourneyOptions()
  const unavailable=!state.capabilities?.scheduled_journey_search||state.results?.data_status==='unavailable'
  const cards=options.map((journey,index)=>{
    const first=journey.legs?.[0],last=journey.legs?.at(-1)
    const duration=Math.round((journey.duration_seconds||0)/60)
    const fare=journey.fare_estimate
    const legs=(journey.legs||[]).map((leg,legIndex)=>`${legIndex?'<span class="route-chain-arrow material-symbols-outlined">chevron_right</span>':''}<span class="route-chain-pill"><span class="material-symbols-outlined">directions_bus</span>${escapeHtml(leg.route_name||leg.route_id)}</span>`).join('')
    const activity=journey.ticketActivity?.complete?`Past ticket volume · ${Math.round(journey.ticketActivity.averagePassengers).toLocaleString('en-IN')} avg`:'Past ticket volume · no match'
    const pick=state.preference==='fastest'?'FASTEST':state.preference==='comfort'?(journey.ticketActivity?.complete?'COMFORT PICK':'NORMAL PICK'):'NORMAL PICK'
    return `<article class="recommended-card result-option"><div class="route-top"><span class="option-label">OPTION ${index+1}</span>${index===0?`<span class="recommended-tag">${pick}</span>`:''}<span class="live-in">${escapeHtml(journey.eta_source||'GTFS schedule')}</span></div><div class="result-option-main"><div><div class="trip-duration">${duration}<small> MIN</small></div><div class="trip-kind">Total scheduled travel time</div></div><div class="result-fare"><span>ESTIMATED FARE</span><b>${fare?.status==='estimated'?`₹${fare.ordinary_adult_total_inr} / ₹${fare.ac_adult_total_inr}`:fare?.status==='partial'?'Partial':'Unavailable'}</b><small>Ordinary / AC adult</small></div></div><div class="route-chain">${legs||'<span class="route-chain-pill">Bus legs unavailable</span>'}</div><div class="result-endpoints"><span><i class="endpoint-dot start"></i>${escapeHtml(first?.from_stop?.stop_name||state.origin?.stop_name)}</span><span><i class="endpoint-dot end"></i>${escapeHtml(last?.to_stop?.stop_name||state.destination?.stop_name)}</span></div><div class="result-meta"><span>${Number(journey.transfers)||0} ${Number(journey.transfers)===1?'change':'changes'} · ${scheduleTime(journey.departure_datetime)}</span><span class="crowd-unknown"><span class="material-symbols-outlined">query_stats</span>${activity}</span></div><button class="primary-action" data-action="open-journey" data-index="${index}">VIEW JOURNEY DETAILS <span class="material-symbols-outlined">arrow_forward</span></button></article>`
  }).join('')
  return `${brandHeader('Journey Results')}<main class="screen results-screen"><div class="result-summary"><span class="summary-point"></span><span>${escapeHtml(state.origin?.stop_name||'Choose origin')}</span><span class="material-symbols-outlined summary-arrow">east</span><span>${escapeHtml(state.destination?.stop_name||'Choose destination')}</span><a href="#home" class="summary-edit" aria-label="Edit journey"><span class="material-symbols-outlined">edit</span></a></div><div class="filter-tabs">${[['fastest','Fastest'],['balanced','Normal'],['comfort','Comfort']].map(([v,l])=>`<button class="filter-tab ${state.preference===v?'active':''}" data-action="preference" data-value="${v}" ${state.journeyLoading?'disabled':''}>${l}</button>`).join('')}</div><div class="result-departure"><span class="material-symbols-outlined">schedule</span>Departing ${scheduleTime(state.departure.toISOString())}<a href="#home">Change</a></div>${state.journeyLoading?'<div class="crowd-state">Loading the saved timetable and searching for scheduled trips…</div>':unavailable?`<div class="crowd-state"><strong>Journey planning unavailable</strong><br>${escapeHtml(state.results?.message||'A validated Delhi GTFS schedule is not currently connected. Stop search and historical stop insights are available.')}</div><button class="primary-action" data-action="retry-search">RETRY JOURNEY SEARCH</button>`:cards||'<div class="crowd-state">The schedule service returned no journeys for these stops and departure time.</div>'}</main>${bottomNav()}`
}
function journeyPage() {
  const journey=state.selectedJourney
  if(!journey) return `${pageHeader('Journey details')}<main class="screen"><div class="crowd-state">This journey is not available in the current session. Search again to choose a backend-confirmed scheduled journey.</div><button class="primary-action" data-route="home">BACK TO JOURNEY SEARCH</button></main>${bottomNav()}`
  const legs=journey.legs||[]
  const tools=`<button class="round-tool" data-action="save" aria-label="Save journey"><span class="material-symbols-outlined">bookmark</span></button><button class="round-tool" data-action="share" aria-label="Share journey"><span class="material-symbols-outlined">share</span></button>`
  const timeline=legs.map((leg,index)=>{const fare=leg.fare_estimate;const perLeg=fare?.status==='estimated'?`Est. ₹${fare.ordinary_adult_fare_inr} ordinary / ₹${fare.ac_adult_fare_inr} AC`:'Fare unavailable';return `<article class="journey-event"><span class="event-node"><span class="material-symbols-outlined">directions_bus</span></span><span class="event-label">${index?'Transfer · ':''}${escapeHtml(leg.route_name||leg.route_id)}</span><h3>${escapeHtml(leg.from_stop?.stop_name||'Boarding stop')}</h3><p>Scheduled departure: ${scheduleTime(leg.departure_datetime)}</p><div class="event-meta"><span>Alight at ${escapeHtml(leg.to_stop?.stop_name||'destination')}</span><span>Arrive ${scheduleTime(leg.arrival_datetime)}</span></div><p class="subtle-note">${escapeHtml(perLeg)}</p></article>`}).join('')
  return `${pageHeader('Journey details','Scheduled itinerary',tools)}<main class="screen"><section class="detail-summary"><div class="route-badges"><span class="route-pill">${legs.length} ${legs.length===1?'leg':'legs'}</span><span class="tradeoff-pill">${Number(journey.transfers)||0} transfers</span></div><div class="place-list"><div class="place-stop">${escapeHtml(legs[0]?.from_stop?.stop_name||state.origin?.stop_name)}</div><div class="place-stop">${escapeHtml(legs.at(-1)?.to_stop?.stop_name||state.destination?.stop_name)}</div></div><div class="detail-stats"><div class="stat-box"><span>Scheduled duration</span><b>${Math.round((journey.duration_seconds||0)/60)}<small style="font-size:12px"> min</small></b></div><div class="stat-box"><span>Waiting</span><b>${Math.round((journey.waiting_seconds||0)/60)}<small style="font-size:12px"> min</small></b></div><div class="stat-box"><span>Ordinary / AC · est.</span><b style="font-size:16px">${escapeHtml(fareCompactText(journey.fare_estimate))}</b></div></div><p class="source-caption">${escapeHtml(state.results?.data_source||'schedule service')} · ${scheduleTime(state.results?.generated_at)}</p></section><div class="timeline-title"><h2>Journey steps</h2><span class="sync-label">${escapeHtml(journey.eta_source||'SCHEDULED')}</span></div><section class="journey-timeline">${timeline||'<div class="crowd-state">No leg detail was returned by the schedule service.</div>'}</section><button class="report-route-btn crowd-status-btn" data-action="journey-crowd"><span class="material-symbols-outlined">insights</span> View crowd status for this route</button><button class="report-route-btn" data-action="report-route"><span class="material-symbols-outlined">flag</span> Report crowding at a stop</button></main>${bottomNav()}`
}
function stopPage() {
  const stopName=state.stopData?.detail?.stop_name||state.stop?.stop_name||''
  const route=state.crowdRoute
  const routeSuggestions=state.crowdRouteMatches.length?`<div class="crowd-route-suggestions">${state.crowdRouteMatches.map(item=>`<button type="button" data-action="choose-crowd-route" data-route-id="${escapeHtml(item.route_id)}"><strong>${escapeHtml(item.route_name)}</strong><span>${escapeHtml(item.route_long_name||'Delhi bus route')}</span></button>`).join('')}</div>`:''
  const routePoints=[6,9,12,15,18,21].map(hour=>{const item=state.crowdActivity.find(row=>row.transaction_hour===hour);return {hour,value:item?.average_passenger_volume??null,transactions:item?.average_transaction_count??null}})
  const observations=state.stopData?.demand?.observations||[]
  const stopPoints=[6,9,12,15,18,21].map(hour=>{const rows=observations.filter(row=>Number(row.transaction_hour)===hour);return {hour,value:rows.length?rows.reduce((sum,row)=>sum+Number(row.passenger_volume||0),0)/rows.length:null}})
  const points=state.crowdMode==='bus'?routePoints:stopPoints
  const validPoints=points.filter(point=>point.value!==null&&point.value!==undefined&&Number.isFinite(Number(point.value)))
  const chart=validPoints.length>1?crowdTrendChart(points):`<div class="crowd-chart-empty">${state.crowdMode==='bus'?'Select a route with matched ticket history to see activity by time.':'No historical ticket series is linked to this GTFS stop yet.'}</div>`
  const currentHour=new Date().getHours()
  const currentPoint=validPoints.reduce((best,item)=>!best||Math.abs(item.hour-currentHour)<Math.abs(best.hour-currentHour)?item:best,null)
  const category=state.stopData?.crowd?.crowd_category?.replaceAll('_',' ')
  const communityStatus=category?`Community reported · ${category}`:'No recent crowd report'
  const mainValue=state.crowdMode==='bus'?currentPoint?.value:state.stopData?.demand?.passenger_volume
  const heading=state.crowdMode==='bus'?(route?`Bus ${route.route_name}`:'Choose a bus route'):stopName||'Choose a bus stop'
  const summaryTitle=state.crowdMode==='bus'?'Historical ticket activity':communityStatus
  const mainStat=state.crowdMode==='bus'?(mainValue==null?'No matched history':`${Math.round(mainValue).toLocaleString('en-IN')} avg passengers`):(category?`${state.stopData?.crowd?.report_count||0} reports`:'No crowd reports')
  const sourceLabel=state.crowdMode==='bus'?'October history · weekday matched':'Community reports · static stop lookup'
  const actions=`<button class="round-tool" data-action="share-crowd" aria-label="Share crowd insights"><span class="material-symbols-outlined">share</span></button>`
  return `${brandHeader('Crowd Reporting')}<main class="screen crowd-insights-screen"><div class="crowd-insights-heading"><button class="back-btn" data-route="home" aria-label="Back"><span class="material-symbols-outlined">arrow_back</span></button><h1><i></i>Crowd Insights</h1>${actions}</div><div class="crowd-mode-tabs"><button class="${state.crowdMode==='bus'?'active':''}" data-action="crowd-mode" data-value="bus"><span class="material-symbols-outlined">directions_bus</span>Bus Crowd</button><button class="${state.crowdMode==='stop'?'active':''}" data-action="crowd-mode" data-value="stop"><span class="material-symbols-outlined">signpost</span>Stop Crowd</button></div>
    ${state.crowdMode==='bus'?`<div class="crowd-lookup"><span class="material-symbols-outlined">directions_bus</span><input data-crowd-route-query value="${escapeHtml(route?route.route_name:state.crowdRouteQuery)}" placeholder="Search a bus route" aria-label="Search a bus route" autocomplete="off"><button data-action="sync-crowd" aria-label="Sync route activity"><span class="material-symbols-outlined">sync</span></button>${routeSuggestions}</div>`:`<label class="crowd-lookup"><span class="material-symbols-outlined">location_on</span><input data-stop-field="stop" value="${escapeHtml(stopName)}" placeholder="Search a bus stop" aria-label="Search a bus stop" autocomplete="off"><span class="suggestions" data-suggestions="stop" hidden></span><button data-action="sync-crowd" aria-label="Sync stop activity"><span class="material-symbols-outlined">sync</span></button></label>`}
    ${state.crowdMode==='stop'&&state.stopLoading?'<div class="crowd-loading"><span class="material-symbols-outlined">sync</span>Loading stop insights…</div>':''}
    <article class="crowd-route-card"><div class="crowd-route-icon"><span class="material-symbols-outlined">${state.crowdMode==='bus'?'directions_bus':'groups'}</span></div><div class="crowd-route-copy"><strong>${escapeHtml(heading)}</strong><small>${state.crowdMode==='bus'?`${route?.route_long_name&&route.route_long_name!==route.route_name?escapeHtml(route.route_long_name):'Historical route activity'}${state.stop?.stop_name?` · From ${escapeHtml(state.stop.stop_name)}`:''}`:'Crowd insights for selected stop'}</small></div><div class="crowd-route-side"><small>${state.crowdMode==='bus'?'DATA':'REPORTS'}</small><b>${state.crowdMode==='bus'?state.crowdActivity.length?`${state.crowdActivity.length} times`:'—':state.stopData?.crowd?.report_count??'—'}</b></div></article>
    <article class="crowd-status-card"><div class="crowd-status-title"><span class="crowd-status-icon material-symbols-outlined">${state.crowdMode==='bus'?'query_stats':'groups'}</span><div><small>${state.crowdMode==='bus'?'HISTORICAL SIGNAL':'COMMUNITY SIGNAL'}</small><h2>${escapeHtml(summaryTitle)}</h2></div></div><strong class="crowd-status-value">${escapeHtml(mainStat)}</strong><div class="crowd-status-footer"><span><span class="material-symbols-outlined">schedule</span>${escapeHtml(state.crowdMode==='bus'?'October history · weekday matched':sourceLabel)}</span><button data-action="sync-crowd"><span class="material-symbols-outlined">sync</span>Sync</button></div></article>
    <article class="crowd-trend-card"><div class="crowd-trend-heading"><div><span class="material-symbols-outlined">analytics</span><h2>${state.crowdMode==='bus'?'Ticket Activity by Time':'Stop Activity by Time'}</h2></div><span>HISTORICAL</span></div>${state.crowdMode==='bus'&&state.crowdActivityLoading?'<div class="crowd-chart-empty">Loading matched weekday history…</div>':chart}<div class="crowd-time-axis">${[6,9,12,15,18,21].map(hour=>`<span>${hour===12?'12 PM':hour<12?`${hour} AM`:`${hour-12} PM`}</span>`).join('')}</div></article>
    ${state.crowdActivityError?`<p class="crowd-inline-error">${escapeHtml(state.crowdActivityError)}</p>`:''}<button class="crowd-report-button" data-action="report-current-crowd"><span class="material-symbols-outlined">group_add</span>Report Current Crowd</button></main>${bottomNav()}`
}
function crowdTrendChart(points){
  const valid=points.filter(point=>point.value!==null&&point.value!==undefined&&Number.isFinite(Number(point.value))),values=valid.map(point=>Number(point.value)),max=Math.max(1,...values),min=Math.min(...values),range=Math.max(1,max-min)
  const coords=valid.map(point=>`${12+(point.hour-6)/15*296},${96-(Number(point.value)-min)/range*68}`)
  const start=coords[0],end=coords.at(-1),endX=end.split(',')[0]
  return `<svg class="crowd-trend-svg" viewBox="0 0 320 112" role="img" aria-label="Historical ticket activity at six times of day"><defs><linearGradient id="crowd-area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#c7653b" stop-opacity=".26"/><stop offset="1" stop-color="#c7653b" stop-opacity="0"/></linearGradient></defs><line x1="0" y1="28" x2="320" y2="28"/><line x1="0" y1="60" x2="320" y2="60"/><line x1="0" y1="96" x2="320" y2="96"/><polygon points="${start} ${coords.join(' ')} ${endX},108 12,108" fill="url(#crowd-area)"/><polyline points="${coords.join(' ')}" fill="none" stroke="#a94d27" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${valid.map((point,index)=>{const [x,y]=coords[index].split(',');return `<circle cx="${x}" cy="${y}" r="4" fill="${Number(point.value)===max?'#a94d27':'#11866a'}"/>`}).join('')}</svg>`
}
const crowdChoices=[['low','sentiment_satisfied','Quiet','Feels lightly crowded','Low'],['moderate','groups','Some crowd','A noticeable crowd is present','Moderate'],['high','groups','Crowded','Busy around the stop','High'],['very_high','pan_tool','Very crowded','Very busy; boarding may be difficult','Very high']]
const feedbackChoices=[['bus_arriving','Bus arriving','directions_bus'],['long_wait','Long wait','schedule'],['service_disruption','Service disruption','warning'],['other','Other','more_horiz']]
function reportPage() {
  if(state.reportSent) return `${pageHeader('Update shared')}<main class="screen"><div class="saved-empty"><span class="material-symbols-outlined">check_circle</span><h2>Thanks for helping riders</h2><p>Your report was sent as a voluntary community observation. It is not a measured passenger count and will expire automatically.</p><button class="primary-action" data-route="home">BACK TO HOME</button></div></main>${bottomNav()}`
  const stop=state.reportStop
  const routeDisplay=state.crowdRoute?.route_id===state.reportRoute?state.crowdRoute.route_name:state.reportRoute
  return `${brandHeader('Crowd Reporting')}<main class="screen"><div class="report-corridor"><i></i><span>${escapeHtml(routeDisplay||'BUS STOP')}</span><span>·</span><span>${escapeHtml(stop?.stop_name||'Choose a stop below')}</span></div><h1 class="report-title">How crowded does it feel right now?</h1><p class="report-intro">Your quick, voluntary report helps riders understand what other people are experiencing.</p><label class="form-label">STOP NAME</label><span class="stop-autocomplete" data-autocomplete="report"><input data-stop-field="report" value="${escapeHtml(stop?.stop_name||'')}" placeholder="Search and select a bus stop" autocomplete="off"><span class="suggestions" data-suggestions="report" hidden></span></span>
    <div class="crowd-options">${crowdChoices.map(([id,icon,title,description,level])=>`<button class="crowd-option ${state.reportCategory===id?'selected':''}" data-action="crowd-category" data-value="${id}"><span class="crowd-option-icon"><span class="material-symbols-outlined">${icon}</span></span><span class="crowd-option-copy"><strong>${title}<span class="crowd-level">${level}</span></strong><small>${description}</small></span><span class="radio-mark"></span></button>`).join('')}</div>
    <div class="section-head"><h2 style="font-size:17px">Quick impressions</h2><span class="kicker">OPTIONAL</span></div><div class="quick-tags">${feedbackChoices.map(([id,label,icon])=>`<button class="quick-tag ${state.reportFeedback===id?'selected':''}" data-action="feedback" data-value="${id}"><span class="material-symbols-outlined" style="font-size:16px;vertical-align:middle">${icon}</span> ${label}</button>`).join('')}</div>
    <button class="report-submit" data-action="submit-report" ${!state.reportCategory||!stop?.id?'disabled':''}>SHARE UPDATE WITH COMMUTERS <span class="material-symbols-outlined">arrow_forward</span></button></main>${bottomNav()}`
}
function ridesPage() {
  let saved
  try { saved=JSON.parse(localStorage.getItem(savedKey)||'[]'); if(!Array.isArray(saved)) saved=[];saved=saved.filter(item=>item?.originId&&item?.destinationId&&Array.isArray(item.legs)&&item.legs.length>0);localStorage.setItem(savedKey,JSON.stringify(saved)) } catch { saved=[] }
  return `${pageHeader('Your rides')}<main class="screen">${saved.length?saved.map((item,i)=>`<article class="saved-item"><span class="kicker">SAVED SCHEDULED JOURNEY · THIS DEVICE</span><h2>${escapeHtml(item.origin)} <span style="color:#98421b">→</span> ${escapeHtml(item.destination)}</h2><p class="subtle-note">${escapeHtml(item.legs?.map(leg=>leg.route_name||leg.route_id).join(' · ')||'Scheduled itinerary')} · saved locally; not synced</p><button class="text-link" data-action="restore-ride" data-index="${i}">Open details →</button><button class="text-link" data-action="remove-ride" data-index="${i}">Remove</button></article>`).join(''):`<div class="saved-empty"><span class="material-symbols-outlined">all_inclusive</span><h2>No saved journeys yet</h2><p>Only journeys confirmed by the schedule service can be saved.</p><button class="primary-action" data-route="home">PLAN A JOURNEY</button></div>`}</main>${bottomNav()}`
}
function authPage() {
  return `${pageHeader('Account')}<main class="screen"><div class="crowd-state"><strong>Accounts are not available yet.</strong><br>Yuktix has no authentication service connected. No credentials are collected or accepted. You can use stop insights and community reporting without signing in.</div><button class="primary-action" data-route="home">CONTINUE WITHOUT AN ACCOUNT</button></main>${bottomNav()}`
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
  return `${brandHeader('Historical Insights')}${pageHeader('Ticket activity','OCTOBER HISTORY')}<main class="screen">${d.loading?'<div class="data-card"><div class="skeleton" style="width:70%"></div><div class="skeleton" style="width:90%;margin-top:16px"></div></div>':d.error?`<div class="crowd-state">Historical insights are unavailable: ${escapeHtml(d.error)}</div><button class="primary-action" data-action="retry-operator">RETRY INSIGHTS</button>`:`<section class="insight-hero"><span class="kicker">SOURCE DATASET</span><h2>Ticket activity overview</h2><p class="subtle-note">${escapeHtml(d.overview?.data_source||'October ETM records')} · historical records</p><div class="detail-stats"><div class="stat-box"><span>Ticket rows</span><b>${escapeHtml(d.overview?.dataset_rows?.toLocaleString?.('en-IN')||'—')}</b></div><div class="stat-box"><span>Days covered</span><b>${escapeHtml(days)}</b></div><div class="stat-box"><span>Route labels</span><b>${escapeHtml(d.overview?.distinct_routes?.toLocaleString?.('en-IN')||'—')}</b></div></div></section><section class="data-card"><div class="demand-head"><div class="demand-title"><span class="material-symbols-outlined" style="color:#98421b">bar_chart</span>Recorded ticket activity</div><span class="soft-tag orange">Historical</span></div><div class="insight-chart">${operatorBars(d.trends)}</div></section><section class="data-card"><div class="section-head"><h2>Route activity</h2><span class="kicker">HISTORICAL</span></div>${routes.length?routes.slice(0,8).map(c=>`<div class="insight-route"><span>${escapeHtml(c.route_label||c.route||'Route')}</span><span>${escapeHtml(c.passenger_volume?.toLocaleString?.('en-IN')??c.transaction_count?.toLocaleString?.('en-IN')??'—')} ticket records</span></div>`).join(''):'<p class="subtle-note">No route activity summary is available.</p>'}</section><button class="report-route-btn" data-route="report"><span class="material-symbols-outlined">campaign</span>Share a rider report</button>`}</main>${bottomNav()}`
}
function render() {
  const nextPage=location.hash.slice(1)||'home'
  if(nextPage==='report'&&state.page!=='report'){state.reportStop=state.stop||state.origin;state.reportCategory=null;state.reportSent=false}
  state.page=nextPage
  const pages={home:homePage,results:resultsPage,journey:journeyPage,stop:stopPage,report:reportPage,rides:ridesPage,auth:authPage,operator:operatorPage}
  app.innerHTML=(pages[state.page]||homePage)()
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
  const [detail,crowd,reports]=await Promise.allSettled([api.searchJourneyStops(stop.stop_name,8),api.crowdAtStop(stop.id),api.reportsAtStop(stop.id)])
  const match=detail.status==='fulfilled'?detail.value.find(item=>item.id===stop.id)||stop:stop
  state.stop={...match};state.stopData={detail:match,demand:null,crowd:crowd.status==='fulfilled'?crowd.value:null,reports:reports.status==='fulfilled'?reports.value:null}
  if(detail.status==='rejected'&&crowd.status==='rejected'&&reports.status==='rejected')state.stopError='Stop information could not be loaded. Check your connection and retry.'
  state.stopLoading=false
  if(state.page==='stop')render()
}
async function resolveStop(field){
  const input=document.querySelector(`[data-stop-field="${field}"]`), query=input?.value?.trim()||''
  const current=field==='origin'?state.origin:field==='destination'?state.destination:field==='stop'?state.stop:state.reportStop
  if(current?.id&&current.stop_name.toLowerCase()===query.toLowerCase())return current
  const matches=await (field==='origin'||field==='destination'?api.searchJourneyStops(query,10):api.searchStops(query,10))
  if(input&&input.value.trim()!==query)return null
  const match=matches.find(s=>s.stop_name.toLowerCase()===query.toLowerCase())
  if(match)return match
  const box=document.querySelector(`[data-suggestions="${field}"]`)
  if(box){box.innerHTML=matches.length?matches.map(s=>suggestionHtml(s,field)).join(''):'<div class="suggestion">No matching stop. Try another name.</div>';box.hidden=false}
  return null
}
function suggestionHtml(stop,field){const coordinates=stop.coordinates&&Number.isFinite(Number(stop.coordinates.latitude))&&Number.isFinite(Number(stop.coordinates.longitude))?`${Number(stop.coordinates.latitude).toFixed(5)}, ${Number(stop.coordinates.longitude).toFixed(5)} · ${stop.coordinate_source==='gtfs_publisher_unverified'?'publisher-listed, not field-verified':'GTFS coordinates'}`:`Stop ID ${escapeHtml(stop.id)} · location not verified`;return `<button type="button" class="suggestion" data-action="choose-stop" data-field="${field}" data-stop-id="${escapeHtml(stop.id)}" data-stop-name="${escapeHtml(stop.stop_name)}"><span>${escapeHtml(stop.stop_name)}</span><small>${coordinates}</small></button>`}
async function showSuggestions(field,query){
  const box=document.querySelector(`[data-suggestions="${field}"]`)
  if(!box)return
  if(query.trim().length<2){box.hidden=true;return}
  const input=document.querySelector(`[data-stop-field="${field}"]`),version=(input._searchVersion||0)+1;input._searchVersion=version
  box.innerHTML='<div class="suggestion">Searching stops…</div>';box.hidden=false
  try{const items=field==='origin'||field==='destination'||field==='report'||(field==='stop'&&state.page==='stop')?await api.searchJourneyStops(query,8):await api.searchStops(query,8);if(input._searchVersion!==version)return;box.innerHTML=items.length?items.map(s=>suggestionHtml(s,field)).join(''):'<div class="suggestion">No matching stops found.</div>'}catch{if(input._searchVersion===version)box.innerHTML='<div class="suggestion">Stop search is unavailable. Check the backend connection.</div>'}
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
    else if(state.capabilities?.scheduled_journey_search){try{state.results=await api.journeySearchV2({origin_stop_id:origin.id,destination_stop_id:destination.id,departure_datetime:state.departure.toISOString(),preference:state.preference,max_transfers:state.selectedRoute?0:1,...(state.selectedRoute?{route_id:state.selectedRoute.route_id}:{})})}catch(error){state.results={data_status:'unavailable',message:error.message};toast(`Journey search failed: ${error.message}`)}}else state.results={data_status:'unavailable',message:'A validated Delhi GTFS timetable is not currently connected.'}
    location.hash='#results'
    if(state.results?.options?.length)loadJourneyTicketActivity(state.results.options)
  }catch(error){state.results={data_status:'unavailable',message:`Stop search failed: ${error.message}`};toast(`Stop search failed: ${error.message}`);location.hash='#results'}
  finally{if(button)button.disabled=false}
}
async function searchRoutes(){
  const input=document.querySelector('[data-route-query]'), query=(input?.value||state.routeQuery).trim()
  if(!query){toast('Enter a bus route number or name.');return}
  state.routeQuery=query
  const box=document.querySelector('[data-route-suggestions]')
  if(box){box.hidden=false;box.innerHTML='<div class="route-suggestion-message">Searching the GTFS route list…</div>'}
  try{state.routeMatches=await api.searchRoutes(query);if(box){box.innerHTML=state.routeMatches.length?state.routeMatches.map(route=>`<button type="button" class="route-suggestion" data-action="select-route" data-route-id="${escapeHtml(route.route_id)}"><span class="route-number">${escapeHtml(route.route_name)}</span><span class="route-match-copy">${escapeHtml(route.route_long_name||'Delhi bus route')}<small>${Number(route.scheduled_trip_count).toLocaleString('en-IN')} scheduled trips</small></span></button>`).join(''):'<div class="route-suggestion-message">No matching routes in the static Delhi GTFS feed.</div>'}}
  catch(error){if(box){box.hidden=false;box.innerHTML=`<div class="route-suggestion-message">Route search unavailable: ${escapeHtml(error.message)}</div>`}}
}
async function searchCrowdRoutes(){
  const input=document.querySelector('[data-crowd-route-query]'),query=(input?.value||state.crowdRouteQuery).trim()
  state.crowdRouteQuery=query;state.crowdRoute=null;state.crowdActivity=[];state.crowdActivityError=null
  if(!query){state.crowdRouteMatches=[];render();return}
  try{state.crowdRouteMatches=await api.searchRoutes(query);if(state.page==='stop'&&state.crowdMode==='bus')render()}
  catch(error){state.crowdRouteMatches=[];state.crowdActivityError=error.message;if(state.page==='stop')render()}
}
async function loadCrowdRouteActivity(){
  if(!state.crowdRoute?.route_id)return
  const current=state.crowdRoute,now=new Date(),date=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`
  state.crowdActivityLoading=true;state.crowdActivityError=null;render()
  const hours=[6,9,12,15,18,21]
  const results=await Promise.allSettled(hours.map(hour=>api.routeActivity(current.route_id,`${date}T${String(hour).padStart(2,'0')}:00:00`)))
  state.crowdActivity=results.filter(result=>result.status==='fulfilled'&&result.value.status==='available').map(result=>result.value).sort((a,b)=>a.transaction_hour-b.transaction_hour)
  if(!state.crowdActivity.length)state.crowdActivityError=results.find(result=>result.status==='rejected')?.reason?.message||'No comparable historical ticket records are available for this route and weekday.'
  state.crowdActivityLoading=false
  if(state.page==='stop'&&state.crowdRoute?.route_id===current.route_id)render()
}
async function refreshCrowdStop(){
  if(!state.stop)return
  try{await loadStopData(state.stop);if(!state.stopError)toast('Stop crowd reports refreshed.')}
  catch(error){toast(`Could not refresh the stop: ${error.message}`)}
}
function chooseCrowdRoute(routeId){
  const route=state.crowdRouteMatches.find(item=>item.route_id===routeId)
  if(!route)return
  state.crowdMode='bus';state.crowdRoute={...route};state.crowdRouteMatches=[];state.crowdRouteQuery='';state.crowdActivity=[];location.hash='#stop';loadCrowdRouteActivity()
}
function seedCrowdFromJourney(journey){
  const leg=journey?.legs?.[0]
  if(!leg)return false
  state.stop={id:leg.from_stop.stop_id,stop_name:leg.from_stop.stop_name}
  state.crowdRoute={route_id:leg.route_id,route_name:leg.route_name||leg.route_id,route_long_name:leg.route_name||leg.route_id}
  state.crowdRouteQuery='';state.crowdRouteMatches=[];state.crowdMode='bus';state.crowdActivity=[];state.crowdActivityError=null;state.stopData=null
  return true
}
async function selectRoute(routeId){
  const route=state.routeMatches.find(item=>item.route_id===routeId)
  if(!route)return
  state.selectedRoute={...route};state.routeStops=[];state.routeLoading=true;state.routeOriginId='';state.routeDestinationId='';render()
  try{const detail=await api.route(routeId);state.selectedRoute={...route,...detail};state.routeStops=detail.stops||[];if(state.routeStops.length>1){state.routeOriginId=state.routeStops[0].stop_id;state.routeDestinationId=state.routeStops.at(-1).stop_id;state.origin={id:state.routeOriginId,stop_name:state.routeStops[0].stop_name};state.destination={id:state.routeDestinationId,stop_name:state.routeStops.at(-1).stop_name}}}
  catch(error){state.routeStops=[];toast(`Could not load this route's stops: ${error.message}`)}
  finally{state.routeLoading=false;state.routeMatches=[];render()}
}
function selectStop(field,stop){
  if(field==='origin')state.origin=stop
  else if(field==='destination')state.destination=stop
  else if(field==='stop'){state.stop=stop;state.stopError=null;state.stopData=null;if(state.page==='stop')loadStopData(stop);else render()}
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
  }catch(error){if(error.status===409)toast('A recent report from this app is already active for this stop.');else if(error.status===429)toast('Report limit reached. Please try again later.');else toast(`Report not sent: ${error.message}`);if(btn){btn.disabled=false;btn.innerHTML='SHARE UPDATE WITH COMMUTERS <span class="material-symbols-outlined">arrow_forward</span>'}}
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
  if(action==='preference'){state.preference=value;render()}
  if(action==='search')await journeySearch()
  if(action==='retry-search')await journeySearch()
  if(action==='retry-capabilities'){state.capabilityError=null;await loadDefaults()}
  if(action==='choose-stop')selectStop(field,{id:stopId,stop_name:stopName})
  if(action==='route-search')await searchRoutes()
  if(action==='select-route')await selectRoute(node.dataset.routeId)
  if(action==='crowd-mode'){
    if(state.page!=='stop'){
      const journey=state.selectedJourney||orderedJourneyOptions()[0]
      if(journey)seedCrowdFromJourney(journey)
      else if(value==='stop')state.stop=state.origin||state.stop
      else if(value==='bus'&&!state.crowdRoute&&state.selectedRoute)state.crowdRoute={...state.selectedRoute,route_name:state.selectedRoute.route_name||state.selectedRoute.route_id}
    }
    state.crowdMode=value
    if(value==='stop'&&state.stop)state.stopData=null
    render()
    if(value==='stop'&&state.stop)loadStopData(state.stop)
    else if(value==='bus'&&state.crowdRoute)loadCrowdRouteActivity()
  }
  if(action==='choose-crowd-route')chooseCrowdRoute(node.dataset.routeId)
  if(action==='sync-crowd'){if(state.crowdMode==='bus')await loadCrowdRouteActivity();else if(state.stop)await refreshCrowdStop();else toast('Search for a stop first.')}
  if(action==='report-current-crowd'){state.reportStop=state.crowdMode==='stop'?state.stop:null;state.reportRoute=state.crowdMode==='bus'?state.crowdRoute?.route_id||null:null;state.reportCategory=null;state.reportFeedback=null;state.reportSent=false;location.hash='#report'}
  if(action==='clear-route'){state.selectedRoute=null;state.routeStops=[];state.routeOriginId='';state.routeDestinationId='';render()}
  if(action==='open-journey'){state.selectedJourney=orderedJourneyOptions()[Number(node.dataset.index)]||null;if(state.selectedJourney)location.hash='#journey';else toast('This itinerary is not available. Search again.')}
  if(action==='journey-crowd'){if(!seedCrowdFromJourney(state.selectedJourney))toast('This journey has no bus leg to show.');else{location.hash='#stop';loadCrowdRouteActivity()}}
  if(action==='open-stop')await openStop()
  if(action==='plan-from-stop'&&state.stop){state.origin=state.stop;state.destination=null;location.hash='#home'}
  if(action==='report-route'){state.stop=state.origin;state.reportStop=state.origin;state.reportRoute=state.selectedJourney?.legs?.[0]?.route_id||null;state.reportCategory=null;state.reportFeedback=null;state.reportSent=false;location.hash='#report'}
  if(action==='report-stop'){state.reportStop=state.stop||state.origin;state.reportRoute=null;state.reportCategory=null;state.reportFeedback=null;state.reportSent=false;location.hash='#report'}
  if(action==='crowd-category'){state.reportCategory=value;render()}
  if(action==='feedback'){state.reportFeedback=state.reportFeedback===value?null:value;render()}
  if(action==='submit-report')await submitReport()
  if(action==='save')saveJourney()
  if(action==='share-crowd'){const text=`Yuktix Crowd Insights · ${state.crowdMode==='bus'?state.crowdRoute?.route_name||'Bus activity':state.stop?.stop_name||'Stop activity'}`;try{if(navigator.share)await navigator.share({title:'Yuktix Crowd Insights',text});else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);toast('Crowd insight copied.')}else toast('Sharing is not supported by this browser.')}catch(error){if(error.name!=='AbortError')toast('Could not share this insight.')}}
  if(action==='share'){if(!state.selectedJourney){toast('There is no confirmed journey to share.');return}const text=`Yuktix scheduled journey: ${state.origin?.stop_name} to ${state.destination?.stop_name}`;try{if(navigator.share)await navigator.share({title:'Yuktix scheduled journey',text});else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);toast('Journey summary copied.')}else toast('Sharing is not supported by this browser.')}catch(error){if(error.name!=='AbortError')toast('Could not share this journey.')}}
  if(action==='restore-ride'){try{const item=JSON.parse(localStorage.getItem(savedKey)||'[]')[Number(node.dataset.index)];if(item?.originId&&item?.destinationId&&Array.isArray(item.legs)&&item.legs.length){state.selectedJourney=item;state.origin={id:item.originId,stop_name:item.origin};state.destination={id:item.destinationId,stop_name:item.destination};location.hash='#journey'}else toast('This saved item has no confirmed schedule details. Remove it and plan again.')}catch{toast('Saved journeys could not be read from browser storage.')}}
  if(action==='remove-ride'){try{const list=JSON.parse(localStorage.getItem(savedKey)||'[]');list.splice(Number(node.dataset.index),1);localStorage.setItem(savedKey,JSON.stringify(list));render()}catch{toast('Could not update browser storage.')}}
  if(action==='retry-stop'&&state.stop)loadStopData(state.stop)
  if(action==='retry-operator'){state.operatorData={loading:true};render();loadOperator()}
}
app.addEventListener('click',clickHandler)
app.addEventListener('input',event=>{
  const crowdRouteInput=event.target.closest('[data-crowd-route-query]')
  if(crowdRouteInput){state.crowdRouteQuery=crowdRouteInput.value;state.crowdRoute=null;state.crowdRouteMatches=[];clearTimeout(crowdRouteInput._searchTimer);crowdRouteInput._searchTimer=setTimeout(()=>searchCrowdRoutes(),240);return}
  const routeInput=event.target.closest('[data-route-query]')
  if(routeInput){state.routeQuery=routeInput.value;state.selectedRoute=null;state.routeStops=[];clearTimeout(routeInput._searchTimer);routeInput._searchTimer=setTimeout(()=>searchRoutes(),240);return}
  const input=event.target.closest('[data-stop-field]');if(!input)return
  const field=input.dataset.stopField
  input._searchVersion=(input._searchVersion||0)+1
  const selected=field==='origin'?state.origin:field==='destination'?state.destination:field==='stop'?state.stop:state.stop
  if(selected&&selected.stop_name.toLowerCase()!==input.value.trim().toLowerCase()){
    state.selectedRoute=null;state.routeStops=[]
    if(field==='origin')state.origin=null
    else if(field==='destination')state.destination=null
    else if(field==='stop')state.stop=null
    else if(field==='report'){state.reportStop=null;state.stop=null}
  }
  clearTimeout(input._searchTimer);input._searchTimer=setTimeout(()=>showSuggestions(field,input.value),180)
})
app.addEventListener('change',event=>{
  const select=event.target.closest('[data-route-stop]');if(!select)return
  const field=select.dataset.routeStop, stop=state.routeStops.find(item=>item.stop_id===select.value);if(!stop)return
  if(field==='origin'){state.routeOriginId=stop.stop_id;state.origin={id:stop.stop_id,stop_name:stop.stop_name}}
  else {state.routeDestinationId=stop.stop_id;state.destination={id:stop.stop_id,stop_name:stop.stop_name}}
  const input=document.querySelector(`[data-stop-field="${field}"]`);if(input)input.value=stop.stop_name
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
