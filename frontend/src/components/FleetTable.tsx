import { AlertCircle, BusFront, ExternalLink, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { getVehicleEtaSnapshots } from '../api'
import type {
  ProjectedVehiclePosition,
  VehicleEtaSnapshot,
  VehicleEtaSnapshotList,
} from '../types'
import { formatClock, formatMinutes, formatPercent } from '../utils/format'

interface FleetTableProps {
  positions: ProjectedVehiclePosition[]
  refreshToken: number
  onOpenVehicle: (vehiclePrefix: string) => void
}

function sourceLabel(snapshot: VehicleEtaSnapshot | undefined) {
  const counts = snapshot?.current_time.service.trip_end.source_counts
  if (!counts) return '—'
  const source = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0]
  return source?.replaceAll('_', ' ') ?? '—'
}

export function FleetTable({ positions, refreshToken, onOpenVehicle }: FleetTableProps) {
  const [snapshots, setSnapshots] = useState<VehicleEtaSnapshotList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [quality, setQuality] = useState<'all' | 'valid' | 'reduced'>('all')

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try {
        setSnapshots(await getVehicleEtaSnapshots(controller.signal))
        setError(null)
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setError(cause instanceof Error ? cause.message : 'Falha ao carregar ETAs da frota')
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), 30_000)
    return () => {
      window.clearInterval(timer)
      controller.abort()
    }
  }, [refreshToken])

  const etaByVehicle = useMemo(
    () => new Map((snapshots?.vehicles ?? []).map((snapshot) => [snapshot.vehicle_prefix, snapshot])),
    [snapshots],
  )
  const rows = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('pt-BR')
    return positions
      .filter((vehicle) => quality === 'all' || vehicle.projection_quality === quality)
      .filter((vehicle) =>
        !normalized ||
        [
          vehicle.vehicle_prefix,
          vehicle.route_short_name,
          vehicle.current_origin_stop_name,
          vehicle.current_destination_stop_name,
          vehicle.headsign,
        ]
          .filter(Boolean)
          .some((value) => value!.toLocaleLowerCase('pt-BR').includes(normalized)),
      )
      .sort((a, b) => {
        const etaA = etaByVehicle.get(a.vehicle_prefix)?.current_time.service.trip_end.estimated_at
        const etaB = etaByVehicle.get(b.vehicle_prefix)?.current_time.service.trip_end.estimated_at
        return (etaA ? Date.parse(etaA) : Infinity) - (etaB ? Date.parse(etaB) : Infinity)
      })
  }, [etaByVehicle, positions, quality, query])

  return (
    <section className="table-page" aria-label="Tabela operacional da frota">
      <div className="table-controls">
        <label className="table-search">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Veículo, linha, origem ou destino"
            aria-label="Filtrar frota"
          />
        </label>
        <select value={quality} onChange={(event) => setQuality(event.target.value as typeof quality)}>
          <option value="all">Todas as projeções</option>
          <option value="valid">Projeção válida</option>
          <option value="reduced">Confiança reduzida</option>
        </select>
        <span className="table-result-count">{rows.length} veículos</span>
      </div>

      {error && <div className="inline-alert"><AlertCircle size={16} /> {error}</div>}

      <div className="data-table-shell">
        <table className="data-table fleet-table">
          <thead>
            <tr>
              <th>Veículo</th>
              <th>Linha</th>
              <th>Trecho atual</th>
              <th>Destino</th>
              <th>Velocidade</th>
              <th>Progresso</th>
              <th>Próxima parada</th>
              <th>ETA terminal atual</th>
              <th>ETA terminal futuro</th>
              <th>Confiança</th>
              <th>Fonte principal</th>
              <th>Atualizado</th>
              <th aria-label="Ações" />
            </tr>
          </thead>
          <tbody>
            {rows.map((vehicle) => {
              const eta = etaByVehicle.get(vehicle.vehicle_prefix)
              const current = eta?.current_time.service.trip_end
              const future = eta?.future_time.service.trip_end
              return (
                <tr key={vehicle.vehicle_prefix}>
                  <td><strong className="vehicle-cell"><BusFront size={15} /> {vehicle.vehicle_prefix}</strong></td>
                  <td><span className="line-chip">{vehicle.route_short_name ?? vehicle.current_line ?? '—'}</span></td>
                  <td className="wide-cell">
                    <span>{vehicle.current_origin_stop_name ?? '—'}</span>
                    <small>→ {vehicle.current_destination_stop_name ?? '—'}</small>
                  </td>
                  <td className="wide-cell">{vehicle.headsign ?? '—'}</td>
                  <td>{vehicle.speed_kmh == null ? '—' : `${Math.round(vehicle.speed_kmh)} km/h`}</td>
                  <td>{formatPercent(vehicle.shape_position)}</td>
                  <td>{formatMinutes(eta?.current_time.service.next_stop.value_seconds)}</td>
                  <td><strong>{formatClock(current?.estimated_at)}</strong><small>{formatMinutes(current?.value_seconds)}</small></td>
                  <td><strong>{formatClock(future?.estimated_at)}</strong><small>{formatMinutes(future?.value_seconds)}</small></td>
                  <td><span className={`quality-badge ${vehicle.projection_quality}`}>{formatPercent(current?.reliability ?? 0)}</span></td>
                  <td className="source-cell">{sourceLabel(eta)}</td>
                  <td>{formatClock(vehicle.source_timestamp)}</td>
                  <td>
                    <button className="row-action" onClick={() => onOpenVehicle(vehicle.vehicle_prefix)} title="Abrir no mapa">
                      <ExternalLink size={15} />
                    </button>
                  </td>
                </tr>
              )
            })}
            {!rows.length && (
              <tr><td colSpan={13} className="empty-table">Nenhum veículo corresponde aos filtros.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <footer className="table-footer">
        ETAs consolidados às {formatClock(snapshots?.generated_at)} · posições atualizadas a cada 10 segundos
      </footer>
    </section>
  )
}
