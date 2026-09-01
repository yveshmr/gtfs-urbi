import { describe, expect, it } from 'vitest'

import type { ProjectedVehiclePosition } from '../types'
import { buildVehicleAlerts } from './vehicleAlerts'

const NOW = Date.parse('2026-08-31T15:10:00Z')
const vehicle = {
  source_timestamp: '2026-08-31T15:04:59Z',
  low_speed_since: '2026-08-31T15:04:59Z',
  speed_kmh: 0.9,
} as ProjectedVehiclePosition

describe('buildVehicleAlerts', () => {
  it('alerta após mais de cinco minutos sem atualização e em baixa velocidade', () => {
    expect(buildVehicleAlerts(vehicle, NOW)).toMatchObject({ stale: true, lowSpeed: true })
  })

  it('não alerta exatamente em cinco minutos', () => {
    const boundary = {
      ...vehicle,
      source_timestamp: '2026-08-31T15:05:00Z',
      low_speed_since: '2026-08-31T15:05:00Z',
    }
    expect(buildVehicleAlerts(boundary, NOW)).toMatchObject({ stale: false, lowSpeed: false })
  })

  it('encerra o alerta de baixa velocidade quando chega a 1 km/h', () => {
    expect(buildVehicleAlerts({ ...vehicle, speed_kmh: 1 }, NOW).lowSpeed).toBe(false)
  })
})
