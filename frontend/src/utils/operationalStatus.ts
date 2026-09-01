import type { VehicleEtaSnapshot, VehicleScheduleContext } from '../types'

export type VehicleDelayStatus = 'no_reference' | 'on_time' | 'warning' | 'delayed'

export interface VehicleOperationalStatus {
  status: VehicleDelayStatus
  delaySeconds: number | null
  estimatedArrivalAt: string | null
  plannedArrivalAt: string | null
}

export function buildVehicleOperationalStatus(
  eta?: VehicleEtaSnapshot,
  schedule?: VehicleScheduleContext,
): VehicleOperationalStatus {
  const estimatedArrivalAt = eta?.current_time.service.trip_end.estimated_at ?? null
  const plannedArrivalAt = schedule?.planned_end_at ?? null
  if (!estimatedArrivalAt || !plannedArrivalAt) {
    return { status: 'no_reference', delaySeconds: null, estimatedArrivalAt, plannedArrivalAt }
  }
  const delaySeconds = Math.round((Date.parse(estimatedArrivalAt) - Date.parse(plannedArrivalAt)) / 1000)
  if (!Number.isFinite(delaySeconds)) {
    return { status: 'no_reference', delaySeconds: null, estimatedArrivalAt, plannedArrivalAt }
  }
  return {
    status: delaySeconds > 10 * 60 ? 'delayed' : delaySeconds > 0 ? 'warning' : 'on_time',
    delaySeconds,
    estimatedArrivalAt,
    plannedArrivalAt,
  }
}
