import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Menu, X, BusFront, ArrowRight } from 'lucide-react'
import { NavLink, Link, Outlet, useLocation, useParams } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import PlannerPage from './pages/PlannerPage'
import JourneyDetailPage from './pages/JourneyDetailPage'
import StopsPage from './pages/StopsPage'
import AnalyticsPage from './pages/AnalyticsPage'
import AuthorityPage from './pages/AuthorityPage'
import MethodologyPage from './pages/MethodologyPage'
import './App.css'

const navigation = [
  { to: '/journeys', label: 'Plan a journey' },
  { to: '/stops', label: 'Stops' },
  { to: '/analytics', label: 'City insights' },
  { to: '/authority', label: 'For authorities' },
  { to: '/methodology', label: 'Our data' },
]

function Shell() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/" aria-label="CrowdWise home" onClick={() => setMenuOpen(false)}>
          <span className="brand-mark"><BusFront size={19} strokeWidth={2.2} /></span>
          <span className="brand-name">crowdwise<span className="brand-period">.</span></span>
        </Link>
        <nav className={`desktop-nav ${menuOpen ? 'is-open' : ''}`} aria-label="Main navigation">
          {navigation.map((item) => (
            <NavLink key={item.to} to={item.to} onClick={() => setMenuOpen(false)}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <Link className="header-cta" to="/journeys">Find a better journey <ArrowRight size={15} /></Link>
        <button className="menu-toggle" type="button" aria-label={menuOpen ? 'Close menu' : 'Open menu'} onClick={() => setMenuOpen(!menuOpen)}>
          {menuOpen ? <X size={21} /> : <Menu size={21} />}
        </button>
      </header>
      <main><Outlet /></main>
      <footer className="site-footer">
        <Link className="brand brand-footer" to="/"><span className="brand-mark"><BusFront size={17} /></span><span className="brand-name">crowdwise<span className="brand-period">.</span></span></Link>
        <span>Historical ticket activity is not a live crowd count.</span>
        <span>Built for more considered journeys in Delhi.</span>
      </footer>
    </div>
  )
}

function JourneyRoute() {
  const { journeyKey } = useParams()
  const location = useLocation()
  return <JourneyDetailPage journey={location.state?.journey} journeyKey={journeyKey ?? ''} />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<LandingPage />} />
          <Route path="journeys" element={<PlannerPage />} />
          <Route path="journey/:journeyKey" element={<JourneyRoute />} />
          <Route path="stops" element={<StopsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="authority" element={<AuthorityPage />} />
          <Route path="methodology" element={<MethodologyPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
