import type {
  FleetPositionResponse,
  TripGeometry,
  VehicleEta,
  VehicleEtaSnapshotList,
  VehicleScheduleContextList,
  VehicleSwapPrescription,
  PersistedSwapDecisionStatus,
  SwapDecision,
  SwapDecisionList,
} from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(
  path: string,
  signal?: AbortSignal,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  const response = await fetch(path, {
    ...init,
    headers,
    signal,
  })
  if (!response.ok) {
    let message = `Falha na API (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // A resposta sem JSON mantém a mensagem baseada no status HTTP.
    }
    throw new ApiError(message, response.status)
  }
  return (await response.json()) as T
}

export function getFleetPositions(signal?: AbortSignal) {
  return request<FleetPositionResponse>('/api/v1/map/vehicles', signal)
}

export function getTripGeometry(tripId: string, signal?: AbortSignal) {
  return request<TripGeometry>(
    `/api/v1/map/trips/${encodeURIComponent(tripId)}/geometry`,
    signal,
  )
}

export function getVehicleEta(vehiclePrefix: string, signal?: AbortSignal) {
  return request<VehicleEta>(
    `/api/v1/vehicles/${encodeURIComponent(vehiclePrefix)}/eta`,
    signal,
  )
}

export function getVehicleEtaSnapshots(signal?: AbortSignal) {
  return request<VehicleEtaSnapshotList>('/api/v1/vehicles/eta-snapshots', signal)
}

export function getVehicleScheduleContexts(signal?: AbortSignal) {
  return request<VehicleScheduleContextList>('/api/v1/vehicles/schedule-contexts', signal)
}

export function getVehicleSwapPrescriptions(signal?: AbortSignal) {
  return request<VehicleSwapPrescription>('/api/v1/prescriptions/vehicle-swaps', signal)
}

export function getVehicleSwapDecisions(signal?: AbortSignal) {
  return request<SwapDecisionList>('/api/v1/prescriptions/vehicle-swap-decisions', signal)
}

export function updateVehicleSwapDecision(
  executionKey: string,
  status: PersistedSwapDecisionStatus,
  updatedBy: string,
  rejectionReason?: string,
  signal?: AbortSignal,
) {
  return request<SwapDecision>('/api/v1/prescriptions/vehicle-swap-decisions', signal, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      execution_key: executionKey,
      status,
      updated_by: updatedBy,
      rejection_reason: rejectionReason,
    }),
  })
}

export function confirmVehicleSwapExecution(
  executionKey: string,
  executedBy: string,
  signal?: AbortSignal,
) {
  return updateVehicleSwapDecision(executionKey, 'executed', executedBy, undefined, signal)
}
