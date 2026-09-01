import type { ProjectedVehiclePosition } from '../types'

export const VEHICLE_ALERT_THRESHOLD_SECONDS = 5 * 60

export interface VehicleAlerts {
  stale: boolean
  lowSpeed: boolean
  sourceAgeSeconds: number | null
  lowSpeedDurationSeconds: number | null
}

function elapsedSeconds(timestamp: string | null | undefined, now: number) {
  if (!timestamp) return null
  const seconds = Math.round((now - Date.parse(timestamp)) / 1000)
  return Number.isFinite(seconds) ? Math.max(0, seconds) : null
}

export function buildVehicleAlerts(
  vehicle: ProjectedVehiclePosition,
  now: number = Date.now(),
): VehicleAlerts {
  const sourceAgeSeconds = elapsedSeconds(vehicle.source_timestamp, now)
  const lowSpeedDurationSeconds = elapsedSeconds(vehicle.low_speed_since, now)
  return {
    stale: sourceAgeSeconds != null && sourceAgeSeconds > VEHICLE_ALERT_THRESHOLD_SECONDS,
    lowSpeed: vehicle.speed_kmh != null && vehicle.speed_kmh < 1 &&
      lowSpeedDurationSeconds != null && lowSpeedDurationSeconds > VEHICLE_ALERT_THRESHOLD_SECONDS,
    sourceAgeSeconds,
    lowSpeedDurationSeconds,
  }
}
