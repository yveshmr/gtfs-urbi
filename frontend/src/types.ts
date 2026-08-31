export interface ProjectedVehiclePosition {
  vehicle_prefix: string
  source_timestamp: string
  projected_at: string
  latitude: number
  longitude: number
  position_source: 'projected'
  gps_direction: number | null
  speed_kmh: number | null
  current_line: string | null
  trip_id: string
  route_id: string
  route_short_name: string | null
  route_long_name: string | null
  headsign: string | null
  direction_id: number | null
  shape_id: string
  shape_position: number
  shape_progress_m: number
  distance_to_shape_m: number
  projection_quality: 'valid' | 'reduced'
  correlation_level: number | null
  current_origin_stop_id: string | null
  current_origin_stop_name: string | null
  current_destination_stop_id: string | null
  current_destination_stop_name: string | null
}

export interface FleetPositionResponse {
  generated_at: string
  count: number
  vehicles: ProjectedVehiclePosition[]
}

export interface TripStop {
  stop_id: string
  stop_code: string | null
  stop_name: string
  stop_sequence: number
  latitude: number | null
  longitude: number | null
  shape_position: number | null
  shape_progress_m: number | null
  projection_quality: string | null
  arrival_seconds: number
  departure_seconds: number
}

export interface LineGeometry {
  type: 'LineString'
  coordinates: [number, number][]
}

export interface TripGeometry {
  trip_id: string
  route_id: string
  route_short_name: string | null
  route_long_name: string | null
  route_color: string | null
  route_text_color: string | null
  headsign: string | null
  direction_id: number | null
  shape_id: string
  geometry: LineGeometry
  stops: TripStop[]
}

export interface EtaTarget {
  value_seconds: number | null
  estimated_at: string | null
  reliability: number
  segments_covered: number
  segments_total: number
  source_counts: Record<string, number>
  complete: boolean
  missing_origin_stop_id: string | null
  missing_destination_stop_id: string | null
}

export interface EtaProjection {
  scope: 'physical' | 'service'
  scenario: 'current_time' | 'future_time'
  next_stop: EtaTarget
  trip_end: EtaTarget
}

export interface EtaScenario {
  physical: EtaProjection
  service: EtaProjection
}

export interface VehicleEta {
  queried_at: string
  vehicle_prefix: string
  trip_id: string
  route_id: string
  direction_id: number
  next_stop_id: string
  terminal_stop_id: string
  remaining_segment_count: number
  current_time: EtaScenario
  future_time: EtaScenario
}

export interface VehicleEtaSnapshot extends VehicleEta {
  generated_at: string
}

export interface VehicleEtaSnapshotList {
  generated_at: string | null
  count: number
  vehicles: VehicleEtaSnapshot[]
}

export interface SwapAssignment {
  commitment_vehicle_prefix: string
  assigned_vehicle_prefix: string
  departure_at: string
  assigned_vehicle_arrival_at: string
  next_line: string | null
  next_direction: string | null
  next_destination: string | null
  next_schedule_position: string | null
  baseline_delay_seconds: number
  proposed_delay_seconds: number
  delay_reduction_seconds: number
  eta_reliability: number
  eta_source_counts: Record<string, number>
  protected: boolean
  changed: boolean
}

export interface TerminalSwapPlan {
  terminal_id: string
  baseline_total_delay_seconds: number
  proposed_total_delay_seconds: number
  saved_delay_seconds: number
  baseline_delayed_trip_count: number
  proposed_delayed_trip_count: number
  baseline_max_delay_seconds: number
  proposed_max_delay_seconds: number
  assignments: SwapAssignment[]
}

export interface VehicleSwapPrescription {
  status: 'ready' | 'no_data' | 'stale'
  evaluated_at: string
  snapshot_generated_at: string | null
  snapshot_age_seconds: number | null
  delay_threshold_minutes: number
  protected_window_minutes: number
  eligible_vehicle_count: number
  terminal_count: number
  plan_count: number
  total_saved_delay_seconds: number
  plans: TerminalSwapPlan[]
}
