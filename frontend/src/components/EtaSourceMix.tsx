import { ETA_SOURCE_LABELS, etaSourceComposition } from '../utils/etaSources'

export function EtaSourceMix({ counts, compact = false }: {
  counts?: Record<string, number>
  compact?: boolean
}) {
  const composition = etaSourceComposition(counts)
  const keys = ['live', 'historical', 'gtfs_planned'] as const
  return (
    <div className={`eta-source-mix ${compact ? 'compact' : ''}`} title="Participação dos trechos restantes no ETA">
      <div className="eta-source-bar" aria-hidden="true">
        {keys.map((key) => composition.percentages[key] > 0 && (
          <i key={key} className={key} style={{ width: `${composition.percentages[key]}%` }} />
        ))}
      </div>
      <div className="eta-source-labels">
        {keys.map((key) => <span key={key} className={key}>{ETA_SOURCE_LABELS[key]} <b>{composition.percentages[key]}%</b></span>)}
      </div>
    </div>
  )
}
