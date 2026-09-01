import { describe, expect, it } from 'vitest'

import type { VehicleEtaSnapshot, VehicleScheduleContext } from '../types'
import { buildVehicleOperationalStatus } from './operationalStatus'

function etaAt(estimatedAt: string): VehicleEtaSnapshot {
  const target = {
    value_seconds: 600,
    estimated_at: estimatedAt,
    reliability: 0.9,
    segments_covered: 1,
    segments_total: 1,
    source_counts: { live: 1 },
    complete: true,
    missing_origin_stop_id: null,
    missing_destination_stop_id: null,
  }
  const physicalCurrent = { scope: 'physical' as const, scenario: 'current_time' as const, next_stop: target, trip_end: target }
  const serviceCurrent = { scope: 'service' as const, scenario: 'current_time' as const, next_stop: target, trip_end: target }
  const physicalFuture = { scope: 'physical' as const, scenario: 'future_time' as const, next_stop: target, trip_end: target }
  const serviceFuture = { scope: 'service' as const, scenario: 'future_time' as const, next_stop: target, trip_end: target }
  return {
    generated_at: '2026-08-31T12:00:00-03:00', queried_at: '2026-08-31T12:00:00-03:00',
    vehicle_prefix: '1001', trip_id: 'trip', route_id: 'route', direction_id: 0,
    next_stop_id: 'next', terminal_stop_id: 'terminal', remaining_segment_count: 1,
    current_time: { physical: physicalCurrent, service: serviceCurrent },
    future_time: { physical: physicalFuture, service: serviceFuture },
  }
}

const schedule = { vehicle_prefix: '1001', planned_end_at: '2026-08-31T13:00:00-03:00' } as VehicleScheduleContext

describe('buildVehicleOperationalStatus', () => {
  it('classifica mais de 10 minutos como atraso crítico', () => {
    expect(buildVehicleOperationalStatus(etaAt('2026-08-31T13:10:01-03:00'), schedule).status).toBe('delayed')
  })

  it('classifica até 10 minutos como atenção', () => {
    expect(buildVehicleOperationalStatus(etaAt('2026-08-31T13:10:00-03:00'), schedule).status).toBe('warning')
  })

  it('mantém sem referência quando não há chegada planejada', () => {
    expect(buildVehicleOperationalStatus(etaAt('2026-08-31T13:00:00-03:00'), undefined).status).toBe('no_reference')
  })
})
