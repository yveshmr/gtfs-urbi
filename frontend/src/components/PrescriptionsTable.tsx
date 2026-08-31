import { AlertCircle, ArrowRight, ArrowRightLeft, CheckCircle2, FilterX, Link2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { getVehicleSwapPrescriptions } from '../api'
import type { ExchangeGroup, SwapAssignment, VehicleSwapPrescription } from '../types'
import { formatClock, formatMinutes, formatPercent } from '../utils/format'
import { ColumnFilter } from './ColumnFilter'

interface PrescriptionsTableProps { refreshToken: number }
interface PrescriptionRow extends SwapAssignment { terminalId: string; groupId: string }

type FilterKey = 'action' | 'group' | 'terminal' | 'departure' | 'originalVehicle'
  | 'assignedVehicle' | 'service' | 'originalArrival' | 'assignedArrival' | 'margin'
  | 'baselineDelay' | 'proposedDelay' | 'reduction' | 'confidence' | 'protection'

const EMPTY_FILTERS: Record<FilterKey, string> = {
  action: '', group: '', terminal: '', departure: '', originalVehicle: '', assignedVehicle: '',
  service: '', originalArrival: '', assignedArrival: '', margin: '', baselineDelay: '',
  proposedDelay: '', reduction: '', confidence: '', protection: '',
}

function signedMinutes(seconds: number) {
  const minutes = Math.round(seconds / 60)
  return `${minutes > 0 ? '+' : ''}${minutes} min`
}

function matches(value: unknown, filter: string) {
  return !filter.trim() || String(value ?? '').toLocaleLowerCase('pt-BR').includes(
    filter.trim().toLocaleLowerCase('pt-BR'),
  )
}

function GroupCard({ group }: { group: ExchangeGroup }) {
  return (
    <article className="exchange-group-card">
      <header>
        <div><span>Grupo de trocas</span><strong>{group.group_id}</strong></div>
        <span className="group-terminal">Terminal {group.terminal_id}</span>
      </header>
      <div className="exchange-chain">
        {group.steps.map((step, index) => (
          <div className="exchange-step" key={`${group.group_id}-${step.commitment_vehicle_prefix}`}>
            {index > 0 && <ArrowRight size={15} />}
            <span><b>{step.assigned_vehicle_prefix}</b><small>assume viagem de {step.commitment_vehicle_prefix}</small></span>
          </div>
        ))}
        <Link2 size={16} className="closed-cycle-icon" aria-label="Ciclo fechado" />
      </div>
      <footer>
        <span><small>Veículos</small><b>{group.vehicle_count}</b></span>
        <span><small>Atraso do grupo</small><b>{formatMinutes(group.baseline_total_delay_seconds)} → {formatMinutes(group.proposed_total_delay_seconds)}</b></span>
        <span><small>Tempo recuperado</small><b className="saved-value">{formatMinutes(group.saved_delay_seconds)}</b></span>
        <span><small>Confiança mínima</small><b>{formatPercent(group.minimum_eta_reliability)}</b></span>
      </footer>
    </article>
  )
}

export function PrescriptionsTable({ refreshToken }: PrescriptionsTableProps) {
  const [data, setData] = useState<VehicleSwapPrescription | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try { setData(await getVehicleSwapPrescriptions(controller.signal)); setError(null) }
      catch (cause) {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setError(cause instanceof Error ? cause.message : 'Falha ao carregar prescrições')
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), 30_000)
    return () => { window.clearInterval(timer); controller.abort() }
  }, [refreshToken])

  const groups = useMemo(() => (data?.plans ?? []).flatMap((plan) => plan.exchange_groups), [data])
  const rows = useMemo(() => (data?.plans ?? []).flatMap((plan) => {
    const groupByAssignment = new Map<string, string>()
    plan.exchange_groups.forEach((group) => group.steps.forEach((step) => {
      groupByAssignment.set(`${step.commitment_vehicle_prefix}|${step.departure_at}`, group.group_id)
    }))
    return plan.assignments.map((assignment) => ({
      ...assignment,
      terminalId: plan.terminal_id,
      groupId: groupByAssignment.get(`${assignment.commitment_vehicle_prefix}|${assignment.departure_at}`) ?? '—',
    }))
  }).filter((row) => showAll || row.changed).filter((row) => {
    const values: Record<FilterKey, unknown> = {
      action: row.changed ? 'Trocar' : 'Manter', group: row.groupId, terminal: row.terminalId,
      departure: formatClock(row.departure_at), originalVehicle: row.commitment_vehicle_prefix,
      assignedVehicle: row.assigned_vehicle_prefix,
      service: `${row.next_line ?? ''} ${row.next_direction ?? ''} ${row.next_destination ?? ''} ${row.next_schedule_position ?? ''}`,
      originalArrival: formatClock(row.commitment_vehicle_arrival_at), assignedArrival: formatClock(row.assigned_vehicle_arrival_at),
      margin: signedMinutes(row.assigned_arrival_margin_seconds), baselineDelay: signedMinutes(row.baseline_delay_seconds),
      proposedDelay: signedMinutes(row.proposed_delay_seconds), reduction: formatMinutes(row.delay_reduction_seconds),
      confidence: formatPercent(row.eta_reliability), protection: row.protected ? 'Protegido' : 'Livre',
    }
    return (Object.keys(filters) as FilterKey[]).every((key) => matches(values[key], filters[key]))
  }).sort((a, b) => a.groupId.localeCompare(b.groupId) || a.departure_at.localeCompare(b.departure_at)), [data, filters, showAll])

  const changedCount = groups.reduce((total, group) => total + group.vehicle_count, 0)
  const setFilter = (key: FilterKey, value: string) => setFilters((current) => ({ ...current, [key]: value }))
  const filter = (key: FilterKey, label: string, placeholder?: string) => (
    <ColumnFilter label={label} value={filters[key]} onChange={(value) => setFilter(key, value)} placeholder={placeholder} />
  )
  const hasFilters = Object.values(filters).some(Boolean)

  return (
    <section className="table-page" aria-label="Prescrições de troca de veículos">
      <div className="prescription-summary">
        <article><span>Grupos de trocas</span><strong>{groups.length}</strong><small>{changedCount} veículos envolvidos</small></article>
        <article><span>Tempo recuperado</span><strong>{formatMinutes(data?.total_saved_delay_seconds)}</strong><small>soma global dos terminais</small></article>
        <article><span>Terminais analisados</span><strong>{data?.terminal_count ?? '—'}</strong><small>{data?.eligible_vehicle_count ?? '—'} veículos elegíveis</small></article>
        <article className={`prescription-status ${data?.status ?? 'no_data'}`}><span>Estado do cálculo</span><strong>{data?.status === 'ready' ? 'Pronto' : data?.status === 'stale' ? 'Desatualizado' : 'Sem dados'}</strong><small>snapshot às {formatClock(data?.snapshot_generated_at)}</small></article>
      </div>

      {groups.length > 0 && <div className="exchange-groups" aria-label="Grupos de trocas recomendados">{groups.map((group) => <GroupCard key={group.group_id} group={group} />)}</div>}

      <div className="table-controls compact-controls">
        <label className="toggle-control"><input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} /> Mostrar alocações sem troca</label>
        <button className="clear-filters" onClick={() => setFilters(EMPTY_FILTERS)} disabled={!hasFilters}><FilterX size={15} /> Limpar filtros</button>
        <span className="table-result-count">{rows.length} ações</span>
      </div>
      {error && <div className="inline-alert"><AlertCircle size={16} /> {error}</div>}

      <div className="data-table-shell">
        <table className="data-table prescription-table enriched-prescription-table">
          <thead>
            <tr>
              <th>Ação</th><th>Grupo</th><th>Terminal</th><th>Partida</th><th>Veículo programado</th><th>Veículo recomendado</th>
              <th>Linha / destino</th><th>Chegada original</th><th>Chegada recomendada</th><th>Folga na chegada</th>
              <th>Atraso original</th><th>Atraso residual</th><th>Redução</th><th>Confiança ETA</th><th>Proteção</th>
            </tr>
            <tr className="column-filter-row">
              <th>{filter('action', 'ação')}</th><th>{filter('group', 'grupo', 'G01')}</th><th>{filter('terminal', 'terminal')}</th><th>{filter('departure', 'partida', 'HH:MM')}</th>
              <th>{filter('originalVehicle', 'veículo programado')}</th><th>{filter('assignedVehicle', 'veículo recomendado')}</th><th>{filter('service', 'linha ou destino')}</th>
              <th>{filter('originalArrival', 'chegada original', 'HH:MM')}</th><th>{filter('assignedArrival', 'chegada recomendada', 'HH:MM')}</th><th>{filter('margin', 'folga', '+min')}</th>
              <th>{filter('baselineDelay', 'atraso original', '+min')}</th><th>{filter('proposedDelay', 'atraso residual', '+min')}</th><th>{filter('reduction', 'redução', 'min')}</th>
              <th>{filter('confidence', 'confiança')}</th><th>{filter('protection', 'proteção')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.terminalId}-${row.commitment_vehicle_prefix}-${row.departure_at}`} className={row.changed ? 'prescribed-row' : ''}>
                <td><span className={`action-badge ${row.changed ? 'swap' : 'keep'}`}>{row.changed ? <ArrowRightLeft size={13} /> : <CheckCircle2 size={13} />}{row.changed ? 'Trocar' : 'Manter'}</span></td>
                <td><span className="group-chip">{row.groupId}</span></td><td><strong>{row.terminalId}</strong></td>
                <td><strong>{formatClock(row.departure_at)}</strong><small>{row.next_schedule_position ?? '—'}</small></td>
                <td>{row.commitment_vehicle_prefix}</td><td><strong className={row.changed ? 'recommended-vehicle' : ''}>{row.assigned_vehicle_prefix}</strong></td>
                <td className="wide-cell"><span>{row.next_line ?? '—'} · {row.next_direction ?? '—'}</span><small>{row.next_destination ?? '—'}</small></td>
                <td>{formatClock(row.commitment_vehicle_arrival_at)}</td><td>{formatClock(row.assigned_vehicle_arrival_at)}</td>
                <td><span className={row.assigned_arrival_margin_seconds >= 0 ? 'saved-value' : 'delay-value baseline'}>{signedMinutes(row.assigned_arrival_margin_seconds)}</span></td>
                <td><span className="delay-value baseline">{signedMinutes(row.baseline_delay_seconds)}</span></td><td><span className="delay-value proposed">{signedMinutes(row.proposed_delay_seconds)}</span></td>
                <td><strong className="saved-value">{formatMinutes(row.delay_reduction_seconds)}</strong></td><td>{formatPercent(row.eta_reliability)}</td>
                <td>{row.protected ? <span className="protected-badge">Protegido</span> : 'Livre'}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={15} className="empty-table">Nenhuma ação corresponde aos filtros.</td></tr>}
          </tbody>
        </table>
      </div>
      <footer className="table-footer">Grupos são ciclos fechados calculados globalmente por terminal · janela protegida de {data?.protected_window_minutes ?? 10} minutos · avaliado às {formatClock(data?.evaluated_at)}</footer>
    </section>
  )
}
