export const ETA_SOURCE_LABELS = {
  live: 'Real',
  historical: 'Histórica',
  gtfs_planned: 'Planejada',
} as const

export type EtaSourceKey = keyof typeof ETA_SOURCE_LABELS

export function etaSourceComposition(counts?: Record<string, number>) {
  const values = {
    live: Math.max(0, counts?.live ?? 0),
    historical: Math.max(0, counts?.historical ?? 0),
    gtfs_planned: Math.max(0, counts?.gtfs_planned ?? 0),
  }
  const total = values.live + values.historical + values.gtfs_planned
  const keys = ['live', 'historical', 'gtfs_planned'] as const
  const raw = Object.fromEntries(keys.map((key) => [key, total ? values[key] / total * 100 : 0])) as Record<EtaSourceKey, number>
  const percentages = Object.fromEntries(keys.map((key) => [key, Math.floor(raw[key])])) as Record<EtaSourceKey, number>
  let remaining = total ? 100 - keys.reduce((sum, key) => sum + percentages[key], 0) : 0
  keys.slice().sort((first, second) => (raw[second] - percentages[second]) - (raw[first] - percentages[first])).forEach((key) => {
    if (remaining > 0) { percentages[key] += 1; remaining -= 1 }
  })
  return {
    total,
    values,
    percentages,
  }
}
