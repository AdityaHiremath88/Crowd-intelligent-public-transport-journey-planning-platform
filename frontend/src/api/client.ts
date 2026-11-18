const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export type Health = {
  status: string
  processed_data_available: boolean
  gtfs_available: boolean
  gtfs_processed_available: boolean
  generated_at: string
}

export type Coordinates = { latitude: number; longitude: number }
export type Stop = {
  id: string
  stop_name: string
  coordinates: Coordinates | null
  demand_available: boolean
}
export type LiveVehicle = {vehicle_id:string; trip_id:string|null; route_id:string|null; latitude:number; longitude:number; bearing:number|null; speed_meters_per_second:number|null; position_timestamp:string; feed_timestamp:string|null; freshness_seconds:number; data_source:string}
export type LiveVehicles = {status:'HEALTHY'|'STALE'|'UNAVAILABLE'|'ERROR'; generated_at:string; last_success_at:string|null; vehicles:LiveVehicle[]; data_source:string}
export type StopSearch = { items: Stop[]; source: string; total_returned: number }
export type StopDetail = Stop & {
  data_source: string
  data_status: 'historical'
  first_observed_date: string | null
  last_observed_date: string | null
  passenger_volume: number
  transaction_count: number
  routes_observed: number
}
export type DemandObservation = {
  date: string
  route: string | null
  day_of_week: number
  transaction_hour: number
  passenger_volume: number
  transaction_count: number
}
export type StopDemand = {
  stop_id: string
  stop_name: string
  passenger_volume: number
  transaction_count: number
  prediction_type: string
  timestamp_basis: string
  status: 'historical'
  data_source: string
  generated_at: string
  days_covered: number
  observation_count: number
  observations_truncated: boolean
  confidence: string
  confidence_note: string
  observations: DemandObservation[]
}
export type Overview = {
  dataset_rows: number
  retained_rows: number
  excluded_rows: number
  dataset_min_timestamp: string
  dataset_max_timestamp: string
  generated_at: string
  distinct_routes: number
  distinct_vehicles: number
  distinct_start_stops: number
  distinct_end_stops: number
  null_vehicle_rows: number
  invalid_passenger_rows: number
  exact_duplicate_rows: number
  passenger_volume_total: number
  passenger_count_mean: number
  null_start_stop_rows: number
  null_end_stop_rows: number
  null_route_rows: number
  data_source: string
  data_status: 'historical'
  occupancy_predictions: 'unavailable'
  caveat: string
}
export type SeriesPoint = { period: string; passenger_volume: number; transaction_count: number }
export type AnalyticsSeries = {
  data_source: string
  data_status: 'historical'
  measure: 'recorded_ticket_volume'
  time_basis: string
  generated_at: string
  points: SeriesPoint[]
}
export type PeakHour = {
  transaction_hour: number
  passenger_volume: number
  transaction_count: number
  observed_dates: number
}
export type PeakHours = {
  data_source: string
  data_status: 'historical'
  day_type: 'all' | 'weekday' | 'weekend'
  time_basis: string
  generated_at: string
  hours: PeakHour[]
}
export type RouteSummary = {
  route: string
  passenger_volume: number
  transaction_count: number
  stop_labels: number
}
export type Corridors = {
  data_source: string
  data_status: 'historical'
  measure: 'recorded_ticket_volume_by_route_label'
  generated_at: string
  routes: RouteSummary[]
}

export type JourneyLeg = {
  trip_id: string
  route_id: string
  route_name: string
  from_stop: { stop_id: string; stop_name: string }
  to_stop: { stop_id: string; stop_name: string }
  departure_datetime: string
  arrival_datetime: string
  stop_sequence: string[]
}
export type JourneyOption = {
  legs: JourneyLeg[]
  departure_datetime: string
  arrival_datetime: string
  duration_seconds: number
  waiting_seconds: number
  transfers: number
  transfer_stops: string[]
  eta_source: string
  crowd_status: 'unavailable'
  score: number
  score_components: Record<string, number | null>
}
export type JourneyResponse = {
  options: JourneyOption[]
  origin_stop_id: string
  destination_stop_id: string
  preference: 'fastest' | 'balanced' | 'comfort'
  data_source: string
  data_status: 'scheduled' | 'unavailable'
  generated_at: string
  crowd_data_available: false
  ranking_note: string
  walking_connections_available: false
  message: string | null
}

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly code?: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError('Cannot reach the CrowdWise API. Check that the backend is running.', 0, 'NETWORK_ERROR')
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = payload?.detail
    const message = typeof detail === 'string'
      ? detail
      : detail?.message ?? `The API returned ${response.status}.`
    throw new ApiError(message, response.status, detail?.code)
  }
  return payload as T
}

export const api = {
  health: () => request<Health>('/health'),
  liveBuses: () => request<LiveVehicles>('/api/v1/vehicles/buses/live'),
  stops: (q = '', source: 'auto' | 'etm' | 'gtfs' = 'auto', limit = 30) => {
    const params = new URLSearchParams({ source, limit: String(limit) })
    if (q) params.set('q', q)
    return request<StopSearch>(`/api/v1/stops?${params}`)
  },
  stop: (stopId: string) => request<StopDetail>(`/api/v1/stops/${encodeURIComponent(stopId)}`),
  demand: (stopId: string) => request<StopDemand>(`/api/v1/stops/${encodeURIComponent(stopId)}/demand`),
  overview: () => request<Overview>('/api/v1/analytics/overview'),
  trends: (granularity: 'day' | 'week' = 'day') =>
    request<AnalyticsSeries>(`/api/v1/analytics/trends?granularity=${granularity}`),
  peakHours: (dayType: 'all' | 'weekday' | 'weekend' = 'all') =>
    request<PeakHours>(`/api/v1/analytics/peak-hours?day_type=${dayType}`),
  corridors: (limit = 20) => request<Corridors>(`/api/v1/analytics/corridors?limit=${limit}`),
  searchJourneys: (body: {
    origin_stop_id: string
    destination_stop_id: string
    departure_datetime: string
    preference: JourneyResponse['preference']
    max_transfers: number
  }) => request<JourneyResponse>('/api/v1/journeys/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  mapStops: (bounds: { south: number; west: number; north: number; east: number }) => {
    const query = new URLSearchParams({ ...Object.fromEntries(Object.entries(bounds).map(([k, v]) => [k, String(v)])) })
    return request<StopSearch>(`/api/v1/stops/map?${query}`)
  },
}
