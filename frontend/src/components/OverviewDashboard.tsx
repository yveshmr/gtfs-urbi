import {
  AlertTriangle,
  ArrowRight,
  ArrowRightLeft,
  BarChart3,
  BusFront,
  Clock3,
  DatabaseZap,
  MapPinned,
  ShieldAlert,
  Sparkles,
  TrendingDown,
} from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

import type {
  ProjectedVehiclePosition,
  SwapExecution,
  VehicleScheduleContext,
  VehicleSwapPrescription,
} from '../types'
import { formatClock, formatMinutes, formatPercent } from '../utils/format'
import type {
  VehicleDelayStatus,
  VehicleOperationalStatus,
} from '../utils/operationalStatus'

interface OverviewDashboardProps {
  vehicles: ProjectedVehiclePosition[]
  statusByVehicle: Map<string, VehicleOperationalStatus>
  scheduleByVehicle: Map<string, VehicleScheduleContext>
  prescription: VehicleSwapPrescription | null
  executions: SwapExecution[]
  generatedAt?: string | null
  map: ReactNode
  onOpenVehicle: (vehiclePrefix: string) => void
  onOpenFleet: (status?: string) => void
  onOpenPrescriptions: () => void
}

const STATUS_LABELS: Record<VehicleDelayStatus, string> = {
  on_time: 'No horário / adiantado',
  warning: 'Até 10 minutos',
  delayed: 'Atraso crítico',
  no_reference: 'Sem referência',
}

function minutesSigned(seconds: number | null) {
  if (seconds == null) return '—'
  const minutes = Math.round(seconds / 60)
  return `${minutes > 0 ? '+' : ''}${minutes} min`
}

export function OverviewDashboard({
  vehicles,
  statusByVehicle,
  scheduleByVehicle,
  prescription,
  executions,
  generatedAt,
  map,
  onOpenVehicle,
  onOpenFleet,
  onOpenPrescriptions,
}: OverviewDashboardProps) {
  const [lineFilter, setLineFilter] = useState('')
  const [terminalFilter, setTerminalFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<VehicleDelayStatus | ''>('')

  const lines = useMemo(() => [...new Set(vehicles.map((vehicle) =>
    scheduleByVehicle.get(vehicle.vehicle_prefix)?.line ??
    vehicle.route_short_name ?? vehicle.current_line,
  ).filter((value): value is string => Boolean(value)))].sort(), [scheduleByVehicle, vehicles])
  const terminals = useMemo(() => [...new Set(vehicles.map((vehicle) =>
    scheduleByVehicle.get(vehicle.vehicle_prefix)?.destination_name,
  ).filter((value): value is string => Boolean(value)))].sort(), [scheduleByVehicle, vehicles])

  const filteredVehicles = useMemo(() => vehicles.filter((vehicle) => {
    const schedule = scheduleByVehicle.get(vehicle.vehicle_prefix)
    const line = schedule?.line ?? vehicle.route_short_name ?? vehicle.current_line
    const status = statusByVehicle.get(vehicle.vehicle_prefix)?.status ?? 'no_reference'
    return (!lineFilter || line === lineFilter) &&
      (!terminalFilter || schedule?.destination_name === terminalFilter) &&
      (!statusFilter || status === statusFilter)
  }), [lineFilter, scheduleByVehicle, statusByVehicle, statusFilter, terminalFilter, vehicles])

  const statusCounts = useMemo(() => filteredVehicles.reduce<Record<VehicleDelayStatus, number>>(
    (counts, vehicle) => {
      const status = statusByVehicle.get(vehicle.vehicle_prefix)?.status ?? 'no_reference'
      counts[status] += 1
      return counts
    },
    { on_time: 0, warning: 0, delayed: 0, no_reference: 0 },
  ), [filteredVehicles, statusByVehicle])
  const referenceCount = filteredVehicles.length - statusCounts.no_reference
  const punctuality = referenceCount ? statusCounts.on_time / referenceCount : 0

  const priorities = useMemo(() => filteredVehicles
    .map((vehicle) => ({ vehicle, status: statusByVehicle.get(vehicle.vehicle_prefix) }))
    .filter((item) => item.status?.delaySeconds != null && item.status.delaySeconds > 0)
    .sort((first, second) => (second.status?.delaySeconds ?? 0) - (first.status?.delaySeconds ?? 0))
    .slice(0, 6), [filteredVehicles, statusByVehicle])

  const delayedLines = useMemo(() => {
    const aggregate = new Map<string, { count: number; totalDelay: number }>()
    filteredVehicles.forEach((vehicle) => {
      const status = statusByVehicle.get(vehicle.vehicle_prefix)
      if (!status?.delaySeconds || status.delaySeconds <= 0) return
      const line = scheduleByVehicle.get(vehicle.vehicle_prefix)?.line ??
        vehicle.route_short_name ?? vehicle.current_line ?? 'Sem linha'
      const current = aggregate.get(line) ?? { count: 0, totalDelay: 0 }
      aggregate.set(line, {
        count: current.count + 1,
        totalDelay: current.totalDelay + status.delaySeconds,
      })
    })
    return [...aggregate.entries()].sort((a, b) => b[1].totalDelay - a[1].totalDelay).slice(0, 5)
  }, [filteredVehicles, scheduleByVehicle, statusByVehicle])

  const executionKeys = useMemo(() => new Set(executions.map((item) => item.execution_key)), [executions])
  const groups = useMemo(() => (prescription?.plans ?? []).flatMap((plan) => plan.exchange_groups), [prescription])
  const pendingGroups = groups.filter((group) => !executionKeys.has(group.execution_key))
  const threatenedTrips = (prescription?.plans ?? []).reduce((total, plan) =>
    total + plan.assignments.filter((item) => item.baseline_delay_seconds > 10 * 60).length, 0)
  const baselineDelay = (prescription?.plans ?? []).reduce(
    (total, plan) => total + plan.baseline_total_delay_seconds, 0,
  )
  const proposedDelay = (prescription?.plans ?? []).reduce(
    (total, plan) => total + plan.proposed_total_delay_seconds, 0,
  )
  const criticalTerminals = [...(prescription?.plans ?? [])]
    .sort((first, second) => second.baseline_total_delay_seconds - first.baseline_total_delay_seconds)
    .slice(0, 5)
  const urgentActions = pendingGroups.flatMap((group) => group.steps.map((step) => ({ group, step })))
    .sort((first, second) => Date.parse(first.step.departure_at) - Date.parse(second.step.departure_at))
    .slice(0, 4)
  const maxTerminalDelay = Math.max(1, ...criticalTerminals.map((plan) => plan.baseline_total_delay_seconds))
  const hasFleetFilters = Boolean(lineFilter || terminalFilter || statusFilter)

  return (
    <section className="manager-overview" aria-label="Visão gerencial da operação">
      <div className="overview-filter-bar">
        <div><BarChart3 size={17} /><span><strong>Recorte da frota</strong><small>Indicadores recalculados instantaneamente</small></span></div>
        <label>Linha<select value={lineFilter} onChange={(event) => setLineFilter(event.target.value)}><option value="">Todas</option>{lines.map((line) => <option key={line}>{line}</option>)}</select></label>
        <label>Terminal de destino<select value={terminalFilter} onChange={(event) => setTerminalFilter(event.target.value)}><option value="">Todos</option>{terminals.map((terminal) => <option key={terminal}>{terminal}</option>)}</select></label>
        <label>Situação<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as VehicleDelayStatus | '')}><option value="">Todas</option>{Object.entries(STATUS_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        {hasFleetFilters && <button onClick={() => { setLineFilter(''); setTerminalFilter(''); setStatusFilter('') }}>Limpar</button>}
      </div>

      <div className="manager-kpi-grid">
        <button className="manager-kpi blue" onClick={() => onOpenFleet()}><BusFront size={19} /><span>Frota monitorada<strong>{filteredVehicles.length}</strong><small>{vehicles.length} veículos no total</small></span></button>
        <button className="manager-kpi green" onClick={() => onOpenFleet('No horário / adiantado')}><TrendingDown size={19} /><span>Pontualidade ETA<strong>{formatPercent(punctuality)}</strong><small>{statusCounts.on_time} de {referenceCount} com referência</small></span></button>
        <button className="manager-kpi orange" onClick={() => onOpenFleet('Atenção')}><Clock3 size={19} /><span>Atenção<strong>{statusCounts.warning}</strong><small>atraso previsto até 10 min</small></span></button>
        <button className="manager-kpi red" onClick={() => onOpenFleet('Atraso crítico')}><AlertTriangle size={19} /><span>Atrasos críticos<strong>{statusCounts.delayed}</strong><small>acima de 10 minutos</small></span></button>
        <button className="manager-kpi yellow" onClick={() => onOpenFleet('Sem referência')}><DatabaseZap size={19} /><span>Sem ETA comparável<strong>{statusCounts.no_reference}</strong><small>sem chegada planejada ou prevista</small></span></button>
        <button className="manager-kpi red" onClick={onOpenPrescriptions}><ShieldAlert size={19} /><span>Viagens ameaçadas<strong>{threatenedTrips}</strong><small>atraso original acima de 10 min</small></span></button>
        <button className="manager-kpi navy" onClick={onOpenPrescriptions}><ArrowRightLeft size={19} /><span>Grupos pendentes<strong>{pendingGroups.length}</strong><small>{groups.length} grupos sugeridos</small></span></button>
        <button className="manager-kpi green" onClick={onOpenPrescriptions}><Sparkles size={19} /><span>Tempo recuperável<strong>{formatMinutes(prescription?.total_saved_delay_seconds)}</strong><small>com as prescrições atuais</small></span></button>
      </div>

      <div className="overview-operation-grid">
        <article className="overview-map-panel">
          <header><div><span className="eyebrow">Distribuição espacial</span><h2>Mapa operacional</h2></div><button onClick={() => onOpenFleet()}>Abrir frota <ArrowRight size={14} /></button></header>
          <div className="overview-map-frame">{map}</div>
        </article>

        <article className="overview-priority-panel">
          <header><div><span className="eyebrow">Ação imediata</span><h2>Prioridades da frota</h2></div><span>Atualizado {formatClock(generatedAt)}</span></header>
          <div className="priority-list">
            {priorities.map(({ vehicle, status }, index) => <button key={vehicle.vehicle_prefix} onClick={() => onOpenVehicle(vehicle.vehicle_prefix)}>
              <span className={`priority-rank ${status?.status}`}>{index + 1}</span>
              <span><strong>{vehicle.vehicle_prefix}</strong><small>Linha {scheduleByVehicle.get(vehicle.vehicle_prefix)?.line ?? vehicle.route_short_name ?? '—'} · {scheduleByVehicle.get(vehicle.vehicle_prefix)?.destination_name ?? vehicle.headsign ?? 'Destino não informado'}</small></span>
              <span className="priority-delay"><strong>{minutesSigned(status?.delaySeconds ?? null)}</strong><small>ETA {formatClock(status?.estimatedArrivalAt)}</small></span>
              <ArrowRight size={15} />
            </button>)}
            {!priorities.length && <div className="overview-empty"><TrendingDown size={22} /><strong>Nenhum atraso no recorte atual</strong></div>}
          </div>
        </article>
      </div>

      <div className="manager-analysis-grid">
        <article className="manager-panel terminal-ranking">
          <header><div><span className="eyebrow">Visão por terminal</span><h2>Terminais mais críticos</h2></div><button onClick={onOpenPrescriptions}>Ver prescrições</button></header>
          <div className="ranking-list">
            {criticalTerminals.map((plan) => <div key={plan.terminal_id}><span><strong>Terminal {plan.terminal_id}</strong><small>{plan.baseline_delayed_trip_count} viagens atrasadas</small></span><div className="ranking-bar"><i style={{ width: `${Math.round((plan.baseline_total_delay_seconds / maxTerminalDelay) * 100)}%` }} /></div><strong>{formatMinutes(plan.baseline_total_delay_seconds)}</strong></div>)}
            {!criticalTerminals.length && <div className="overview-empty">Sem terminais críticos no cálculo atual.</div>}
          </div>
        </article>

        <article className="manager-panel line-ranking">
          <header><div><span className="eyebrow">Concentração</span><h2>Linhas com maior atraso</h2></div></header>
          <div className="line-delay-list">
            {delayedLines.map(([line, values], index) => <div key={line}><span className="line-position">{index + 1}</span><span><strong>Linha {line}</strong><small>{values.count} veículos com atraso</small></span><strong>{formatMinutes(values.totalDelay)}</strong></div>)}
            {!delayedLines.length && <div className="overview-empty">Sem atrasos nas linhas do recorte.</div>}
          </div>
        </article>

        <article className="manager-panel prescription-impact">
          <header><div><span className="eyebrow">Resultado potencial</span><h2>Impacto das prescrições</h2></div></header>
          <div className="impact-comparison">
            <div><span>Sem intervenção</span><strong>{formatMinutes(baselineDelay)}</strong><i><b style={{ width: '100%' }} /></i></div>
            <div><span>Após recomendação</span><strong>{formatMinutes(proposedDelay)}</strong><i><b style={{ width: `${baselineDelay ? Math.max(3, Math.round((proposedDelay / baselineDelay) * 100)) : 0}%` }} /></i></div>
          </div>
          <div className="impact-result"><TrendingDown size={18} /><span><small>Redução potencial</small><strong>{formatMinutes(Math.max(0, baselineDelay - proposedDelay))}</strong></span></div>
        </article>
      </div>

      <article className="urgent-actions-panel">
        <header><div><span className="eyebrow">Fila de decisão</span><h2>Próximas ações recomendadas</h2></div><button onClick={onOpenPrescriptions}>Abrir plano completo <ArrowRight size={14} /></button></header>
        <div className="urgent-action-list">
          {urgentActions.map(({ group, step }) => <div key={`${group.execution_key}-${step.commitment_vehicle_prefix}`}>
            <span className="action-clock"><Clock3 size={14} />{formatClock(step.departure_at)}</span>
            <span><small>Terminal {group.terminal_id} · Grupo {group.group_id}</small><strong>Usar {step.assigned_vehicle_prefix} na viagem de {step.commitment_vehicle_prefix}</strong></span>
            <span><small>Viagem</small><strong>Linha {step.next_line ?? '—'} · {step.next_destination ?? '—'}</strong></span>
            <span><small>Atraso residual</small><strong>{minutesSigned(step.proposed_delay_seconds)}</strong></span>
          </div>)}
          {!urgentActions.length && <div className="overview-empty"><Sparkles size={20} /> Nenhuma ação pendente.</div>}
        </div>
      </article>
    </section>
  )
}
