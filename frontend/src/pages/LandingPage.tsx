import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3, Clock3, Database, MapPin, Route, UsersRound } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type AnalyticsSeries, type Health, type Overview } from '../api/client'
import MapPanel from '../components/MapPanel'
import MetricCard from '../components/MetricCard'
import Notice from '../components/Notice'

const number = (value: number | undefined) => value == null ? '—' : value.toLocaleString('en-IN')

export default function LandingPage() {
  const [health, setHealth] = useState<Health | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [series, setSeries] = useState<AnalyticsSeries | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([api.health(), api.overview(), api.trends('day')])
      .then(([healthData, overviewData, trendData]) => {
        if (!active) return
        setHealth(healthData); setOverview(overviewData); setSeries(trendData)
      })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'API unavailable') })
    return () => { active = false }
  }, [])

  return (
    <>
      <section className="hero-section page-wrap">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-line" />DELHI · BUILT AROUND THE JOURNEY</div>
          <h1>Move through<br />the city with<br /><em>more context.</em></h1>
          <p className="hero-lede">A bus planner shaped by the people who ride. Compare scheduled trips with historical ticket activity—always with a clear view of what the data can and cannot tell us.</p>
          <div className="hero-actions">
            <Link className="button button-dark" to="/journeys">Plan a journey <ArrowRight size={17} /></Link>
            <Link className="text-link" to="/analytics">Explore the data <ArrowDownRight size={16} /></Link>
          </div>
          <div className="hero-meta"><span className={`status-dot ${health?.processed_data_available ? 'status-dot-good' : ''}`} />{health?.processed_data_available ? 'October 2026 ticket data connected' : 'Connecting to historical data'}</div>
        </div>
        <div className="hero-visual">
          <div className="hero-map-frame"><MapPanel compact /></div>
          <div className="hero-floating-note"><span className="floating-note-icon"><Route size={16} /></span><span><strong>Journey search</strong><small>{health?.gtfs_processed_available ? 'GTFS schedule ready' : 'Waiting on a verified GTFS feed'}</small></span><ArrowUpRight size={16} className="muted-icon" /></div>
          <div className="hero-stamp"><span>01</span><span>DELHI<br />BUS DATA</span></div>
        </div>
      </section>

      {!health?.gtfs_processed_available && <div className="page-wrap hero-notice-wrap"><Notice tone="warning" title="Scheduled journey search is not connected yet.">We have not found a current authorized Delhi bus GTFS feed. Journey results remain unavailable until one can be verified; no sample routes are shown as real.</Notice></div>}
      {error && <div className="page-wrap"><Notice tone="warning" title="The backend could not be reached.">{error}</Notice></div>}

      <section className="data-band">
        <div className="page-wrap band-inner">
          <div><span className="band-kicker">THE DATA WE CAN STAND BEHIND</span><h2>Evidence, with its edges visible.</h2></div>
          <p>Ticket records can reveal patterns in recorded activity. They cannot tell us how many people are waiting or exactly how full a bus is. CrowdWise keeps that distinction in the product.</p>
          <Link to="/methodology" className="round-link" aria-label="Read our methodology"><ArrowRight size={19} /></Link>
        </div>
      </section>

      <section className="page-wrap metrics-section">
        <div className="section-intro"><div><span className="eyebrow">A MONTH IN THE RECORDS</span><h2>One real dataset.<br /><em>Clear boundaries.</em></h2></div><p>Historical October 2026 ETM records, processed locally with DuckDB. The numbers describe recorded ticket activity, not physical occupancy.</p></div>
        <div className="metrics-grid">
          <MetricCard label="Ticket transactions" value={number(overview?.dataset_rows)} detail="Records retained from October 1–31" icon={<Database size={17} />} />
          <MetricCard label="Passenger volume" value={number(overview?.passenger_volume_total)} detail="Sum of passenger_count across tickets" icon={<UsersRound size={17} />} />
          <MetricCard label="Route labels" value={number(overview?.distinct_routes)} detail="Distinct normalized ETM route labels" icon={<Route size={17} />} />
          <MetricCard label="Vehicle IDs missing" value={overview ? `${Math.round(overview.null_vehicle_rows / overview.dataset_rows * 100)}%` : '—'} detail="Records without a usable vehicle number" icon={<BarChart3 size={17} />} />
        </div>
      </section>

      <section className="page-wrap split-section">
        <div className="split-copy"><span className="eyebrow">READ THE PATTERN, NOT A PROMISE</span><h2>When are tickets<br />being recorded?</h2><p>The curve below uses transaction timestamps. It is useful for historical analysis, but it is not a verified boarding-time or crowd forecast.</p><Link to="/analytics" className="button button-outline">Open city insights <ArrowRight size={16} /></Link></div>
        <div className="chart-card landing-chart">
          <div className="chart-title-row"><div><strong>Recorded passenger volume</strong><small>Daily · October 2026 · transaction-date basis</small></div><span className="chart-badge"><Clock3 size={13} />HISTORICAL</span></div>
          {series ? <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={series.points} margin={{ top: 12, right: 5, left: -14, bottom: 0 }}>
              <defs><linearGradient id="landingFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#719681" stopOpacity={0.25} /><stop offset="95%" stopColor="#719681" stopOpacity={0.01} /></linearGradient></defs>
              <CartesianGrid vertical={false} stroke="#e8ece6" />
              <XAxis dataKey="period" tickFormatter={(value: string) => value.slice(8)} tickLine={false} axisLine={false} tick={{ fill: '#8b9690', fontSize: 11 }} interval={4} />
              <YAxis tickLine={false} axisLine={false} tick={{ fill: '#8b9690', fontSize: 11 }} tickFormatter={(value: number) => `${Math.round(value / 1000)}k`} />
              <Tooltip formatter={(value) => [number(Number(value)), 'Recorded passenger volume']} labelFormatter={(label) => `Date · ${label}`} />
              <Area type="monotone" dataKey="passenger_volume" stroke="#315c49" strokeWidth={2.4} fill="url(#landingFill)" activeDot={{ r: 4, fill: '#d7f36b', stroke: '#315c49' }} />
            </AreaChart>
          </ResponsiveContainer> : <div className="chart-empty">Historical series unavailable.</div>}
          <div className="chart-footnote">Source: October Delhi ETM CSV · `created_at` is transaction time</div>
        </div>
      </section>

      <section className="page-wrap feature-section">
        <div className="feature-head"><div><span className="eyebrow">THREE WAYS TO LOOK CLOSER</span><h2>Better decisions start<br />with better questions.</h2></div><Link className="text-link" to="/methodology">How we handle uncertainty <ArrowRight size={15} /></Link></div>
        <div className="feature-grid">
          <Link to="/journeys" className="feature-card"><span className="feature-index">01 / COMMUTER</span><Route size={21} /><h3>Plan the trip</h3><p>Compare scheduled bus options when a verified timetable is available.</p><span className="feature-link">Open planner <ArrowRight size={15} /></span></Link>
          <Link to="/analytics" className="feature-card"><span className="feature-index">02 / CITY</span><BarChart3 size={21} /><h3>See the pattern</h3><p>Explore ticket volume by hour, day, stop label and route label.</p><span className="feature-link">Explore insights <ArrowRight size={15} /></span></Link>
          <Link to="/authority" className="feature-card"><span className="feature-index">03 / AUTHORITY</span><MapPin size={21} /><h3>Find the signals</h3><p>Review recorded demand patterns alongside coverage and data quality.</p><span className="feature-link">Open dashboard <ArrowRight size={15} /></span></Link>
        </div>
      </section>
    </>
  )
}
