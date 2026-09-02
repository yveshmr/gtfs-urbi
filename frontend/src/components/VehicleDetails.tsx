import {
  AlertCircle,
  ArrowRight,
  BusFront,
  CircleGauge,
  Clock3,
  Gauge,
  MapPin,
  Route,
  X,
} from 'lucide-react'

import type {
  EtaTarget,
  ProjectedVehiclePosition,
  TripGeometry,
  VehicleEta,
  VehicleScheduleContext,
} from '../types'
import {
  formatClock,
  formatDistance,
  formatMinutes,
  formatPercent,
} from '../utils/format'
import type { VehicleOperationalStatus } from '../utils/operationalStatus'
import type { VehicleAlerts } from '../utils/vehicleAlerts'
import { EtaSourceMix } from './EtaSourceMix'

interface VehicleDetailsProps {
  vehicle: ProjectedVehiclePosition
  geometry: TripGeometry | null
  eta: VehicleEta | null
  schedule: VehicleScheduleContext | null
  operationalStatus?: VehicleOperationalStatus
  alerts?: VehicleAlerts
  loading: boolean
  error: string | null
  onClose: () => void
}

function EtaCard({ label, target, accent }: { label: string; target?: EtaTarget; accent: string }) {
  return (
    <article className="eta-card" style={{ '--eta-accent': accent } as React.CSSProperties}>
      <span className="eta-label">{label}</span>
      <strong>{formatMinutes(target?.value_seconds)}</strong>
      <span className="eta-clock">Previsão {formatClock(target?.estimated_at)}</span>
      <div className="reliability-row">
        <span>Confiabilidade</span>
        <b>{target ? formatPercent(target.reliability) : '—'}</b>
      </div>
      <div className="reliability-track">
        <span style={{ width: `${Math.round((target?.reliability ?? 0) * 100)}%` }} />
      </div>
      <EtaSourceMix counts={target?.source_counts} />
    </article>
  )
}

export function VehicleDetails({
  vehicle,
  geometry,
  eta,
  schedule,
  operationalStatus,
  alerts,
  loading,
  error,
  onClose,
}: VehicleDetailsProps) {
  const currentTripEnd = eta?.current_time.service.trip_end
  const futureTripEnd = eta?.future_time.service.trip_end
  const nextStop = eta?.future_time.service.next_stop
  const statusLabels = {
    delayed: 'Atraso crítico',
    warning: 'Atenção',
    on_time: 'No horário',
    no_reference: 'Sem referência planejada',
  }
  const delayMinutes = operationalStatus?.delaySeconds == null
    ? '—'
    : `${operationalStatus.delaySeconds > 0 ? '+' : ''}${Math.round(operationalStatus.delaySeconds / 60)} min`

  return (
    <aside className="vehicle-panel" aria-label={`Detalhes do veículo ${vehicle.vehicle_prefix}`}>
      <header className="vehicle-panel-header">
        <div className="vehicle-avatar"><BusFront size={24} /></div>
        <div>
          <span className="eyebrow">Veículo selecionado</span>
          <h2>{vehicle.vehicle_prefix}</h2>
        </div>
        <button className="icon-button close-button" onClick={onClose} aria-label="Fechar detalhes">
          <X size={20} />
        </button>
      </header>

      <div className="vehicle-route-heading">
        <div>
          <span>Linha</span>
          <strong>{vehicle.route_short_name ?? vehicle.current_line ?? '—'}</strong>
        </div>
        <ArrowRight size={20} />
        <div className="destination-heading">
          <span>Destino</span>
          <strong>{vehicle.headsign ?? geometry?.headsign ?? 'Não informado'}</strong>
        </div>
      </div>

      <div className="vehicle-facts">
        <div><Gauge size={17} /><span>Velocidade</span><strong>{vehicle.speed_kmh?.toFixed(0) ?? '—'} km/h</strong></div>
        <div><Route size={17} /><span>Progresso</span><strong>{Math.round(vehicle.shape_position * 100)}%</strong></div>
        <div><MapPin size={17} /><span>Distância do shape</span><strong>{formatDistance(vehicle.distance_to_shape_m)}</strong></div>
        <div><CircleGauge size={17} /><span>Projeção</span><strong>{vehicle.projection_quality === 'valid' ? 'Válida' : 'Reduzida'}</strong></div>
      </div>

      {(alerts?.stale || alerts?.lowSpeed) && <section className="vehicle-operational-alerts" aria-label="Alertas do veículo">
        {alerts.stale && <div className="stale"><AlertCircle size={16} /><span><strong>Sem atualização</strong><small>Último dado há {formatMinutes(alerts.sourceAgeSeconds)}</small></span></div>}
        {alerts.lowSpeed && <div className="low-speed"><Gauge size={16} /><span><strong>Abaixo de 1 km/h</strong><small>Condição mantida há {formatMinutes(alerts.lowSpeedDurationSeconds)}</small></span></div>}
      </section>}

      <section className="current-segment-card">
        <div className="section-title"><span className="orange-dot" />Trecho atual</div>
        <div className="segment-stops">
          <span>{vehicle.current_origin_stop_name ?? vehicle.current_origin_stop_id ?? 'Origem'}</span>
          <ArrowRight size={16} />
          <strong>{vehicle.current_destination_stop_name ?? vehicle.current_destination_stop_id ?? 'Próxima parada'}</strong>
        </div>
      </section>

      <section className={`arrival-status-card ${operationalStatus?.status ?? 'no_reference'}`}>
        <div className="arrival-status-heading">
          <span>Chegada ao terminal</span>
          <strong>{statusLabels[operationalStatus?.status ?? 'no_reference']}</strong>
        </div>
        <div className="arrival-status-times">
          <div><span>Planejada</span><strong>{formatClock(schedule?.planned_end_at)}</strong></div>
          <ArrowRight size={16} />
          <div><span>Prevista pelo ETA</span><strong>{formatClock(operationalStatus?.estimatedArrivalAt)}</strong></div>
          <div className="arrival-delay"><span>Desvio</span><strong>{delayMinutes}</strong></div>
        </div>
      </section>

      <section className="eta-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Estimativas operacionais</span>
            <h3>ETA até o terminal</h3>
          </div>
          <Clock3 size={20} />
        </div>
        {loading && <div className="panel-message">Calculando estimativas…</div>}
        {error && <div className="panel-message panel-error">{error}</div>}
        {!loading && (
          <div className="eta-grid">
            <EtaCard label="Trânsito atual" target={currentTripEnd} accent="#49C0E8" />
            <EtaCard label="Cenário futuro" target={futureTripEnd} accent="#009CDF" />
          </div>
        )}
      </section>

      <section className="next-stop-card">
        <span>Próxima parada</span>
        <strong>
          {geometry?.stops.find((stop) => stop.stop_id === eta?.next_stop_id)?.stop_name ??
            vehicle.current_destination_stop_name ??
            eta?.next_stop_id ??
            '—'}
        </strong>
        <div><Clock3 size={15} /> {formatMinutes(nextStop?.value_seconds)} · {formatClock(nextStop?.estimated_at)}</div>
      </section>

      <footer className="vehicle-panel-footer">
        <span>Atualizado às {formatClock(vehicle.source_timestamp)}</span>
        <span>{geometry?.stops.length ?? 0} paradas na viagem</span>
      </footer>
    </aside>
  )
}
