import { AlertCircle, BusFront, ExternalLink, FilterX } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { getVehicleEtaSnapshots, getVehicleScheduleContexts } from '../api'
import type {
  ProjectedVehiclePosition,
  VehicleEtaSnapshot,
  VehicleEtaSnapshotList,
  VehicleScheduleContextList,
} from '../types'
import { formatClock, formatPercent } from '../utils/format'
import { ColumnFilter } from './ColumnFilter'

interface FleetTableProps {
  positions: ProjectedVehiclePosition[]
  refreshToken: number
  onOpenVehicle: (vehiclePrefix: string) => void
}

type FilterKey =
  | 'vehicle' | 'line' | 'direction' | 'table' | 'origin' | 'destination'
  | 'plannedStart' | 'actualStart' | 'plannedEnd' | 'eta' | 'arrivalDelay'
  | 'departureDelay' | 'status' | 'speed' | 'confidence' | 'updated'

const EMPTY_FILTERS: Record<FilterKey, string> = {
  vehicle: '', line: '', direction: '', table: '', origin: '', destination: '',
  plannedStart: '', actualStart: '', plannedEnd: '', eta: '', arrivalDelay: '',
  departureDelay: '', status: '', speed: '', confidence: '', updated: '',
}

function sourceLabel(snapshot: VehicleEtaSnapshot | undefined) {
  const counts = snapshot?.current_time.service.trip_end.source_counts
  if (!counts) return '—'
  const source = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0]
  return source?.replaceAll('_', ' ') ?? '—'
}

function differenceSeconds(later?: string | null, earlier?: string | null) {
  if (!later || !earlier) return null
  const value = Math.round((Date.parse(later) - Date.parse(earlier)) / 1000)
  return Number.isFinite(value) ? value : null
}

function signedMinutes(seconds: number | null) {
  if (seconds == null) return '—'
  const minutes = Math.round(seconds / 60)
  return `${minutes > 0 ? '+' : ''}${minutes} min`
}

function operationalStatus(delay: number | null) {
  if (delay == null) return 'Sem referência'
  if (delay > 0) return 'Atrasado'
  if (delay < 0) return 'Adiantado'
  return 'No horário'
}

function matches(value: unknown, filter: string) {
  return !filter.trim() || String(value ?? '').toLocaleLowerCase('pt-BR').includes(
    filter.trim().toLocaleLowerCase('pt-BR'),
  )
}

export function FleetTable({ positions, refreshToken, onOpenVehicle }: FleetTableProps) {
  const [snapshots, setSnapshots] = useState<VehicleEtaSnapshotList | null>(null)
  const [scheduleContexts, setScheduleContexts] = useState<VehicleScheduleContextList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      const [etaResult, scheduleResult] = await Promise.allSettled([
        getVehicleEtaSnapshots(controller.signal),
        getVehicleScheduleContexts(controller.signal),
      ])
      if (controller.signal.aborted) return
      const failures: string[] = []
      if (etaResult.status === 'fulfilled') setSnapshots(etaResult.value)
      else failures.push(etaResult.reason instanceof Error ? etaResult.reason.message : 'Falha nos ETAs')
      if (scheduleResult.status === 'fulfilled') setScheduleContexts(scheduleResult.value)
      else failures.push(scheduleResult.reason instanceof Error ? scheduleResult.reason.message : 'Falha nas viagens')
      setError(failures.length ? failures.join(' · ') : null)
    }
    void load()
    const timer = window.setInterval(() => void load(), 30_000)
    return () => { window.clearInterval(timer); controller.abort() }
  }, [refreshToken])

  const etaByVehicle = useMemo(
    () => new Map((snapshots?.vehicles ?? []).map((item) => [item.vehicle_prefix, item])),
    [snapshots],
  )
  const scheduleByVehicle = useMemo(
    () => new Map((scheduleContexts?.vehicles ?? []).map((item) => [item.vehicle_prefix, item])),
    [scheduleContexts],
  )
  const rows = useMemo(() => positions.map((vehicle) => {
    const eta = etaByVehicle.get(vehicle.vehicle_prefix)
    const schedule = scheduleByVehicle.get(vehicle.vehicle_prefix)
    const estimatedAt = eta?.current_time.service.trip_end.estimated_at
    const arrivalDelay = differenceSeconds(estimatedAt, schedule?.planned_end_at)
    const departureDelay = differenceSeconds(schedule?.actual_start_at, schedule?.planned_start_at)
    return { vehicle, eta, schedule, estimatedAt, arrivalDelay, departureDelay, status: operationalStatus(arrivalDelay) }
  }).filter(({ vehicle, eta, schedule, estimatedAt, arrivalDelay, departureDelay, status }) => {
    const values: Record<FilterKey, unknown> = {
      vehicle: vehicle.vehicle_prefix,
      line: schedule?.line ?? vehicle.route_short_name ?? vehicle.current_line,
      direction: schedule?.direction ?? vehicle.direction_id,
      table: schedule?.schedule_table,
      origin: schedule?.origin_name ?? vehicle.current_origin_stop_name,
      destination: schedule?.destination_name ?? vehicle.current_destination_stop_name ?? vehicle.headsign,
      plannedStart: formatClock(schedule?.planned_start_at),
      actualStart: formatClock(schedule?.actual_start_at),
      plannedEnd: formatClock(schedule?.planned_end_at), eta: formatClock(estimatedAt),
      arrivalDelay: signedMinutes(arrivalDelay), departureDelay: signedMinutes(departureDelay), status,
      speed: vehicle.speed_kmh == null ? '' : Math.round(vehicle.speed_kmh),
      confidence: formatPercent(eta?.current_time.service.trip_end.reliability ?? 0),
      updated: formatClock(vehicle.source_timestamp),
    }
    return (Object.keys(filters) as FilterKey[]).every((key) => matches(values[key], filters[key]))
  }).sort((a, b) => (a.estimatedAt ? Date.parse(a.estimatedAt) : Infinity) - (b.estimatedAt ? Date.parse(b.estimatedAt) : Infinity)), [etaByVehicle, filters, positions, scheduleByVehicle])

  const setFilter = (key: FilterKey, value: string) => setFilters((current) => ({ ...current, [key]: value }))
  const hasFilters = Object.values(filters).some(Boolean)
  const filter = (key: FilterKey, label: string, placeholder?: string) => (
    <ColumnFilter label={label} value={filters[key]} onChange={(value) => setFilter(key, value)} placeholder={placeholder} />
  )

  return (
    <section className="table-page" aria-label="Tabela operacional da frota">
      <div className="table-controls compact-controls">
        <div><strong>Visão operacional consolidada</strong><small>Modelo 4 + GTFS + Consultar Viagens + ETA calculado</small></div>
        <button className="clear-filters" onClick={() => setFilters(EMPTY_FILTERS)} disabled={!hasFilters}><FilterX size={15} /> Limpar filtros</button>
        <span className="table-result-count">{rows.length} veículos</span>
      </div>
      {error && <div className="inline-alert"><AlertCircle size={16} /> {error}</div>}
      <div className="data-table-shell">
        <table className="data-table fleet-table enriched-fleet-table">
          <thead>
            <tr>
              <th>Veículo</th><th>Linha</th><th>Sentido</th><th>Tabela</th><th>Origem</th><th>Destino / terminal</th>
              <th>Partida planejada</th><th>Partida real</th><th>Chegada planejada</th><th>ETA terminal</th>
              <th>Atraso chegada</th><th>Atraso partida</th><th>Status</th><th>Velocidade</th><th>Confiança / fonte</th><th>Atualizado</th><th aria-label="Ações" />
            </tr>
            <tr className="column-filter-row">
              <th>{filter('vehicle', 'veículo', 'Prefixo')}</th><th>{filter('line', 'linha')}</th><th>{filter('direction', 'sentido')}</th><th>{filter('table', 'tabela')}</th>
              <th>{filter('origin', 'origem')}</th><th>{filter('destination', 'destino')}</th><th>{filter('plannedStart', 'partida planejada', 'HH:MM')}</th>
              <th>{filter('actualStart', 'partida real', 'HH:MM')}</th><th>{filter('plannedEnd', 'chegada planejada', 'HH:MM')}</th><th>{filter('eta', 'ETA', 'HH:MM')}</th>
              <th>{filter('arrivalDelay', 'atraso de chegada', '+min')}</th><th>{filter('departureDelay', 'atraso de partida', '+min')}</th><th>{filter('status', 'status')}</th>
              <th>{filter('speed', 'velocidade')}</th><th>{filter('confidence', 'confiança')}</th><th>{filter('updated', 'atualização', 'HH:MM')}</th><th />
            </tr>
          </thead>
          <tbody>
            {rows.map(({ vehicle, eta, schedule, estimatedAt, arrivalDelay, departureDelay, status }) => {
              const confidence = eta?.current_time.service.trip_end.reliability ?? 0
              return (
                <tr key={vehicle.vehicle_prefix}>
                  <td><strong className="vehicle-cell"><BusFront size={15} /> {vehicle.vehicle_prefix}</strong></td>
                  <td><span className="line-chip">{schedule?.line ?? vehicle.route_short_name ?? vehicle.current_line ?? '—'}</span></td>
                  <td>{schedule?.direction ?? vehicle.direction_id ?? '—'}</td><td>{schedule?.schedule_table ?? '—'}</td>
                  <td className="wide-cell">{schedule?.origin_name ?? vehicle.current_origin_stop_name ?? '—'}</td>
                  <td className="wide-cell">{schedule?.destination_name ?? vehicle.current_destination_stop_name ?? vehicle.headsign ?? '—'}</td>
                  <td>{formatClock(schedule?.planned_start_at)}</td><td>{formatClock(schedule?.actual_start_at)}</td><td>{formatClock(schedule?.planned_end_at)}</td>
                  <td><strong>{formatClock(estimatedAt)}</strong></td>
                  <td><span className={`delay-value ${arrivalDelay != null && arrivalDelay > 0 ? 'baseline' : 'proposed'}`}>{signedMinutes(arrivalDelay)}</span></td>
                  <td>{signedMinutes(departureDelay)}</td><td><span className="operation-status">{status}</span></td>
                  <td>{vehicle.speed_kmh == null ? '—' : `${Math.round(vehicle.speed_kmh)} km/h`}</td>
                  <td><span className={`quality-badge ${vehicle.projection_quality}`}>{formatPercent(confidence)}</span><small>{sourceLabel(eta)}</small></td>
                  <td>{formatClock(vehicle.source_timestamp)}</td>
                  <td><button className="row-action" onClick={() => onOpenVehicle(vehicle.vehicle_prefix)} title="Abrir no mapa"><ExternalLink size={15} /></button></td>
                </tr>
              )
            })}
            {!rows.length && <tr><td colSpan={17} className="empty-table">Nenhum veículo corresponde aos filtros.</td></tr>}
          </tbody>
        </table>
      </div>
      <footer className="table-footer">
        ETAs às {formatClock(snapshots?.generated_at)} · viagens às {formatClock(scheduleContexts?.generated_at)}{scheduleContexts?.status === 'stale' ? ' (cache temporariamente desatualizado)' : ''} · sem persistência do payload de Consultar Viagens
      </footer>
    </section>
  )
}
