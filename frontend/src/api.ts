import type {
  FleetPositionResponse,
  TripGeometry,
  VehicleEta,
} from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
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
