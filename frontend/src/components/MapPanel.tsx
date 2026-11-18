import { useCallback, useEffect, useState } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import { LocateFixed, MapPin } from 'lucide-react'
import { api, type LiveVehicles } from '../api/client'

export default function MapPanel({ compact = false }: { compact?: boolean }) {
  const [feed, setFeed] = useState<LiveVehicles | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(async () => {
    try { setFeed(await api.liveBuses()); setError(null) }
    catch { setError('Live bus positions could not be loaded. Check that the backend is running.') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 30_000); return () => window.clearInterval(timer) }, [refresh])
  const vehicles = feed?.vehicles ?? []
  const updated = feed?.last_success_at ? new Date(feed.last_success_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}) : null

  return (
    <section className={`map-panel ${compact ? 'map-panel-compact' : ''}`} aria-label="Interactive map of Delhi">
      <div className="map-overlay-label"><span className="map-label-icon"><MapPin size={15} /></span><span>DELHI · LIVE BUSES</span></div>
      <MapContainer center={[28.6139, 77.209]} zoom={10} scrollWheelZoom className="leaflet-map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {vehicles.map((vehicle) => (
          <CircleMarker
            key={vehicle.vehicle_id}
            center={[vehicle.latitude, vehicle.longitude]}
            radius={compact ? 4 : 6}
            pathOptions={{ color: '#142B45', weight: 2, fillColor: '#E87535', fillOpacity: 1 }}
          >
            <Popup><strong>Bus {vehicle.vehicle_id}</strong><br />Route: {vehicle.route_id ?? 'Not matched'}<br />Trip: {vehicle.trip_id ?? 'Not available'}<br /><small>Position age: {vehicle.freshness_seconds}s · live vehicle position</small></Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      {(loading || error || !vehicles.length) && <div className="map-unavailable"><LocateFixed size={16} /><span>{loading ? 'Loading live vehicle positions…' : error ?? (feed?.status === 'STALE' ? 'Feed is stale; no current positions shown.' : 'No current bus positions are available.')}</span></div>}
      {!!vehicles.length && <div className="map-count">{vehicles.length.toLocaleString()} buses · {feed?.status === 'HEALTHY' ? 'LIVE' : 'STALE'}{updated ? ` · updated ${updated}` : ''}</div>}
      <div className="map-credit">Vehicle positions from Delhi Transport Stack GTFS-Realtime · refreshed every 30 seconds</div>
    </section>
  )
}
