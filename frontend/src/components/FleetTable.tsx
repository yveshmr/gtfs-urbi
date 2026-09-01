import { AlertCircle, BusFront, ExternalLink, FilterX } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { getVehicleEtaSnapshots, getVehicleScheduleContexts } from '../api'
import type {
  ProjectedVehiclePosition,
  VehicleEtaSnapshot,
  VehicleEtaSnapshotList,
  VehicleScheduleContext,
  VehicleScheduleContextList,
} from '../types'
import { formatClock, formatMinutes, formatPercent } from '../utils/format'
import { classifyVehicleDelay } from '../utils/operationalStatus'
import { buildVehicleAlerts, type VehicleAlerts } from '../utils/vehicleAlerts'
import { ColumnFilter } from './ColumnFilter'
import { compareSortValues, SortableHeader, type SortState } from './SortableHeader'

interface FleetTableProps {
  positions: ProjectedVehiclePosition[]
  refreshToken: number
  presetStatus?: string | null
  presetToken?: number
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

interface FleetRow {
  vehicle: ProjectedVehiclePosition
  eta?: VehicleEtaSnapshot
  schedule?: VehicleScheduleContext
  estimatedAt?: string | null
  arrivalDelay: number | null
  departureDelay: number | null
  status: string
  statusKey: 'on-time' | 'warning' | 'delayed' | 'no-reference'
  alerts: VehicleAlerts
}

function sortValue(row: FleetRow, key: FilterKey): unknown {
  const { vehicle, eta, schedule } = row
  const values: Record<FilterKey, unknown> = {
    vehicle: vehicle.vehicle_prefix,
    line: schedule?.line ?? vehicle.route_short_name ?? vehicle.current_line,
    direction: schedule?.direction ?? vehicle.direction_id,
    table: schedule?.schedule_table,
    origin: schedule?.origin_name ?? vehicle.current_origin_stop_name,
    destination: schedule?.destination_name ?? vehicle.current_destination_stop_name ?? vehicle.headsign,
    plannedStart: schedule?.planned_start_at,
    actualStart: schedule?.actual_start_at,
    plannedEnd: schedule?.planned_end_at,
    eta: row.estimatedAt,
    arrivalDelay: row.arrivalDelay,
    departureDelay: row.departureDelay,
    status: row.status,
    speed: vehicle.speed_kmh,
    confidence: eta?.current_time.service.trip_end.reliability,
    updated: vehicle.source_timestamp,
  }
  return values[key]
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
  const status = classifyVehicleDelay(delay)
  const labels = {
    no_reference: { label: 'Sem referência', key: 'no-reference' as const },
    delayed: { label: 'Atraso crítico', key: 'delayed' as const },
    warning: { label: 'Atenção', key: 'warning' as const },
    on_time: { label: 'No horário / adiantado', key: 'on-time' as const },
  }
  return labels[status]
}

function matches(value: unknown, filter: string) {
  return !filter.trim() || String(value ?? '').toLocaleLowerCase('pt-BR').includes(
    filter.trim().toLocaleLowerCase('pt-BR'),
  )
}

export function FleetTable({
  positions,
  refreshToken,
  presetStatus,
  presetToken,
  onOpenVehicle,
}: FleetTableProps) {
  const [snapshots, setSnapshots] = useState<VehicleEtaSnapshotList | null>(null)
  const [scheduleContexts, setScheduleContexts] = useState<VehicleScheduleContextList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [sort, setSort] = useState<SortState<FilterKey>>({ key: 'eta', direction: 'asc' })
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    setFilters({ ...EMPTY_FILTERS, status: presetStatus ?? '' })
  }, [presetStatus, presetToken])

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
  const rows = useMemo(() => positions.map((vehicle): FleetRow => {
    const eta = etaByVehicle.get(vehicle.vehicle_prefix)
    const schedule = scheduleByVehicle.get(vehicle.vehicle_prefix)
    const estimatedAt = eta?.current_time.service.trip_end.estimated_at
    const arrivalDelay = differenceSeconds(estimatedAt, schedule?.planned_end_at)
    const departureDelay = differenceSeconds(schedule?.actual_start_at, schedule?.planned_start_at)
    const status = operationalStatus(arrivalDelay)
    const alerts = buildVehicleAlerts(vehicle, now)
    return {
      vehicle, eta, schedule, estimatedAt, arrivalDelay, departureDelay,
      status: status.label, statusKey: status.key, alerts,
    }
  }).filter(({ vehicle, eta, schedule, estimatedAt, arrivalDelay, departureDelay, status, alerts }) => {
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
      arrivalDelay: signedMinutes(arrivalDelay), departureDelay: signedMinutes(departureDelay),
      status: `${status} ${alerts.stale ? 'Sem atualização' : ''} ${alerts.lowSpeed ? 'Abaixo de 1 km/h por 5 min' : ''}`,
      speed: vehicle.speed_kmh == null ? '' : Math.round(vehicle.speed_kmh),
      confidence: formatPercent(eta?.current_time.service.trip_end.reliability ?? 0),
      updated: formatClock(vehicle.source_timestamp),
    }
    return (Object.keys(filters) as FilterKey[]).every((key) => matches(values[key], filters[key]))
  }).sort((first, second) => {
    return compareSortValues(sortValue(first, sort.key), sortValue(second, sort.key), sort.direction)
  }), [etaByVehicle, filters, now, positions, scheduleByVehicle, sort])

  const setFilter = (key: FilterKey, value: string) => setFilters((current) => ({ ...current, [key]: value }))
  const hasFilters = Object.values(filters).some(Boolean)
  const handleSort = (key: FilterKey) => setSort((current) => ({
    key,
    direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
  }))
  const header = (key: FilterKey, label: string) => (
    <SortableHeader columnKey={key} label={label} sort={sort} onSort={handleSort} />
  )
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
        <table className="data-table fleet-table fleet-compact-table">
          <thead>
            <tr>
              <th>{header('vehicle', 'Veículo')}</th><th>{header('line', 'Linha')}</th><th>{header('direction', 'Sentido')}</th><th>{header('table', 'Tabela')}</th>
              <th>{header('origin', 'Origem')}</th><th>{header('destination', 'Destino')}</th><th>{header('plannedStart', 'Partida plan.')}</th>
              <th>{header('actualStart', 'Partida real')}</th><th>{header('plannedEnd', 'Chegada plan.')}</th><th>{header('eta', 'ETA terminal')}</th>
              <th>{header('arrivalDelay', 'Atraso cheg.')}</th><th>{header('departureDelay', 'Atraso part.')}</th><th>{header('status', 'Status')}</th>
              <th>{header('speed', 'Vel.')}</th><th>{header('confidence', 'Confiança')}</th><th>{header('updated', 'Atualizado')}</th><th aria-label="Ações" />
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
            {rows.map(({ vehicle, eta, schedule, estimatedAt, arrivalDelay, departureDelay, status, statusKey, alerts }) => {
              const confidence = eta?.current_time.service.trip_end.reliability ?? 0
              return (
                <tr key={vehicle.vehicle_prefix} className={`fleet-status-row ${statusKey} ${alerts.stale ? 'stale-alert' : ''} ${alerts.lowSpeed ? 'low-speed-alert' : ''}`}>
                  <td><strong className="vehicle-cell"><BusFront size={15} /> {vehicle.vehicle_prefix}</strong></td>
                  <td><span className="line-chip">{schedule?.line ?? vehicle.route_short_name ?? vehicle.current_line ?? '—'}</span></td>
                  <td>{schedule?.direction ?? vehicle.direction_id ?? '—'}</td><td>{schedule?.schedule_table ?? '—'}</td>
                  <td className="compact-location-cell" title={schedule?.origin_name ?? vehicle.current_origin_stop_name ?? undefined}>{schedule?.origin_name ?? vehicle.current_origin_stop_name ?? '—'}</td>
                  <td className="compact-location-cell" title={schedule?.destination_name ?? vehicle.current_destination_stop_name ?? vehicle.headsign ?? undefined}>{schedule?.destination_name ?? vehicle.current_destination_stop_name ?? vehicle.headsign ?? '—'}</td>
                  <td>{formatClock(schedule?.planned_start_at)}</td><td>{formatClock(schedule?.actual_start_at)}</td><td>{formatClock(schedule?.planned_end_at)}</td>
                  <td><strong>{formatClock(estimatedAt)}</strong></td>
                  <td><span className={`delay-value ${arrivalDelay != null && arrivalDelay > 0 ? 'baseline' : 'proposed'}`}>{signedMinutes(arrivalDelay)}</span></td>
                  <td>{signedMinutes(departureDelay)}</td><td><span className={`operation-status ${statusKey}`}>{status}</span>{alerts.stale && <small className="vehicle-alert-badge stale">Sem atualização há {formatMinutes(alerts.sourceAgeSeconds)}</small>}{alerts.lowSpeed && <small className="vehicle-alert-badge low-speed">Abaixo de 1 km/h há {formatMinutes(alerts.lowSpeedDurationSeconds)}</small>}</td>
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
