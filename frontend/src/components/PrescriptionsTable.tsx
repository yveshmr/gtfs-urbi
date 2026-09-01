import {
  AlertCircle, ArrowRight, ArrowRightLeft, CheckCircle2, Clock3, FilterX,
  ListChecks, Network, ShieldCheck, Sparkles, X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import {
  confirmVehicleSwapExecution,
  getVehicleScheduleContexts,
  getVehicleSwapExecutions,
  getVehicleSwapPrescriptions,
} from '../api'
import type {
  ExchangeGroup, SwapAssignment, SwapExecution, VehicleScheduleContext,
  VehicleScheduleContextList, VehicleSwapPrescription,
} from '../types'
import { formatClock, formatMinutes, formatPercent } from '../utils/format'
import { ColumnFilter } from './ColumnFilter'
import { compareSortValues, SortableHeader, type SortState } from './SortableHeader'

interface PrescriptionsTableProps { refreshToken: number }
interface PrescriptionRow extends SwapAssignment {
  terminalId: string
  groupId: string
  execution?: SwapExecution
}
type PrescriptionView = 'groups' | 'table'
type FilterKey = 'action' | 'group' | 'terminal' | 'departure' | 'originalVehicle'
  | 'assignedVehicle' | 'service' | 'originalArrival' | 'assignedArrival' | 'margin'
  | 'baselineDelay' | 'proposedDelay' | 'reduction' | 'confidence' | 'protection' | 'execution'

const EMPTY_FILTERS: Record<FilterKey, string> = {
  action: '', group: '', terminal: '', departure: '', originalVehicle: '', assignedVehicle: '',
  service: '', originalArrival: '', assignedArrival: '', margin: '', baselineDelay: '',
  proposedDelay: '', reduction: '', confidence: '', protection: '', execution: '',
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

function urgency(group: ExchangeGroup) {
  return Math.min(...group.steps.map((step) => Date.parse(step.departure_at)))
}

function urgencyLabel(group: ExchangeGroup) {
  const seconds = Math.round((urgency(group) - Date.now()) / 1000)
  return seconds >= 0 ? `Primeira saída em ${formatMinutes(seconds)}` : `Saída vencida há ${formatMinutes(-seconds)}`
}

function rowSortValue(row: PrescriptionRow, key: FilterKey): unknown {
  const values: Record<FilterKey, unknown> = {
    action: row.changed ? 'Trocar' : 'Manter', group: row.groupId, terminal: row.terminalId,
    departure: row.departure_at, originalVehicle: row.commitment_vehicle_prefix,
    assignedVehicle: row.assigned_vehicle_prefix,
    service: `${row.next_line ?? ''} ${row.next_destination ?? ''}`,
    originalArrival: row.commitment_vehicle_arrival_at,
    assignedArrival: row.assigned_vehicle_arrival_at,
    margin: row.assigned_arrival_margin_seconds, baselineDelay: row.baseline_delay_seconds,
    proposedDelay: row.proposed_delay_seconds, reduction: row.delay_reduction_seconds,
    confidence: row.eta_reliability, protection: row.protected ? 1 : 0,
    execution: row.execution?.executed_at,
  }
  return values[key]
}

function ExchangeGroupCard({
  group, execution, scheduleByVehicle, onExecute,
}: {
  group: ExchangeGroup
  execution?: SwapExecution
  scheduleByVehicle: Map<string, VehicleScheduleContext>
  onExecute: (group: ExchangeGroup) => void
}) {
  return (
    <article className={`exchange-plan-card ${execution ? 'executed' : ''}`}>
      <header className="exchange-plan-header">
        <div>
          <span className="group-kicker">Grupo {group.group_id}</span>
          <strong>Terminal {group.terminal_id}</strong>
          <small>{group.vehicle_count} veículos em ciclo fechado</small>
        </div>
        <div className="group-status-stack">
          <span className={`urgency-badge ${urgency(group) < Date.now() ? 'late' : ''}`}><Clock3 size={13} /> {urgencyLabel(group)}</span>
          {execution && <span className="executed-badge"><CheckCircle2 size={13} /> Executado</span>}
        </div>
      </header>

      <div className="group-impact-strip">
        <div><span>Tempo recuperado</span><strong>{formatMinutes(group.saved_delay_seconds)}</strong></div>
        <div><span>Atraso total</span><strong>{formatMinutes(group.baseline_total_delay_seconds)} <ArrowRight size={13} /> {formatMinutes(group.proposed_total_delay_seconds)}</strong></div>
        <div><span>Pior atraso</span><strong>{formatMinutes(group.baseline_max_delay_seconds)} <ArrowRight size={13} /> {formatMinutes(group.proposed_max_delay_seconds)}</strong></div>
        <div><span>Confiança mínima</span><strong>{formatPercent(group.minimum_eta_reliability)}</strong></div>
      </div>

      <div className="group-action-list">
        {group.steps.map((step, index) => {
          const assignedSchedule = scheduleByVehicle.get(step.assigned_vehicle_prefix)
          return (
            <div className="group-action-row" key={`${group.execution_key}-${step.commitment_vehicle_prefix}`}>
              <div className="action-order">{index + 1}</div>
              <div className="action-instruction">
                <span>Ação recomendada</span>
                <strong>Usar <b>{step.assigned_vehicle_prefix}</b> na viagem de {step.commitment_vehicle_prefix}</strong>
                <small>Linha {step.next_line ?? '—'} · {step.next_destination ?? 'Destino não informado'}</small>
              </div>
              <div className="action-time"><span>Chegada planejada</span><strong>{formatClock(assignedSchedule?.planned_end_at)}</strong></div>
              <div className="action-time forecast"><span>Chegada prevista</span><strong>{formatClock(step.assigned_vehicle_arrival_at)}</strong><small>original {formatClock(step.commitment_vehicle_arrival_at)}</small></div>
              <div className="action-time"><span>Saída planejada</span><strong>{formatClock(step.departure_at)}</strong><small>{step.next_schedule_position ?? '—'}</small></div>
              <div className="action-time"><span>Folga</span><strong className={step.assigned_arrival_margin_seconds >= 0 ? 'saved-value' : 'delay-value baseline'}>{signedMinutes(step.assigned_arrival_margin_seconds)}</strong><small>atraso {signedMinutes(step.proposed_delay_seconds)}</small></div>
            </div>
          )
        })}
      </div>

      <footer className="exchange-plan-footer">
        {execution ? (
          <span><ShieldCheck size={16} /> Confirmado por <strong>{execution.executed_by}</strong> às {formatClock(execution.executed_at)}</span>
        ) : (
          <button onClick={() => onExecute(group)}><CheckCircle2 size={16} /> Confirmar execução do grupo</button>
        )}
      </footer>
    </article>
  )
}

export function PrescriptionsTable({ refreshToken }: PrescriptionsTableProps) {
  const [data, setData] = useState<VehicleSwapPrescription | null>(null)
  const [executions, setExecutions] = useState<SwapExecution[]>([])
  const [scheduleContexts, setScheduleContexts] = useState<VehicleScheduleContextList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<PrescriptionView>('groups')
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [sort, setSort] = useState<SortState<FilterKey>>({ key: 'departure', direction: 'asc' })
  const [showAll, setShowAll] = useState(false)
  const [confirmingGroup, setConfirmingGroup] = useState<ExchangeGroup | null>(null)
  const [operatorName, setOperatorName] = useState(() => window.sessionStorage.getItem('gtfs-on-time-operator') ?? '')
  const [confirming, setConfirming] = useState(false)
  const [confirmationError, setConfirmationError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      const results = await Promise.allSettled([
        getVehicleSwapPrescriptions(controller.signal),
        getVehicleSwapExecutions(controller.signal),
        getVehicleScheduleContexts(controller.signal),
      ])
      if (controller.signal.aborted) return
      const failures: string[] = []
      if (results[0].status === 'fulfilled') setData(results[0].value)
      else failures.push(results[0].reason instanceof Error ? results[0].reason.message : 'Falha nas prescrições')
      if (results[1].status === 'fulfilled') setExecutions(results[1].value.executions)
      else failures.push(results[1].reason instanceof Error ? results[1].reason.message : 'Falha nas confirmações')
      if (results[2].status === 'fulfilled') setScheduleContexts(results[2].value)
      else failures.push(results[2].reason instanceof Error ? results[2].reason.message : 'Falha nos horários')
      setError(failures.length ? failures.join(' · ') : null)
    }
    void load()
    const timer = window.setInterval(() => void load(), 30_000)
    return () => { window.clearInterval(timer); controller.abort() }
  }, [refreshToken])

  const executionByKey = useMemo(() => new Map(executions.map((item) => [item.execution_key, item])), [executions])
  const scheduleByVehicle = useMemo(() => new Map((scheduleContexts?.vehicles ?? []).map((item) => [item.vehicle_prefix, item])), [scheduleContexts])
  const groups = useMemo(() => (data?.plans ?? []).flatMap((plan) => plan.exchange_groups).sort((first, second) => {
    const firstExecuted = executionByKey.has(first.execution_key)
    const secondExecuted = executionByKey.has(second.execution_key)
    if (firstExecuted !== secondExecuted) return firstExecuted ? 1 : -1
    return urgency(first) - urgency(second) || second.saved_delay_seconds - first.saved_delay_seconds
  }), [data, executionByKey])

  const rows = useMemo(() => (data?.plans ?? []).flatMap((plan) => {
    const groupByAssignment = new Map<string, ExchangeGroup>()
    plan.exchange_groups.forEach((group) => group.steps.forEach((step) => {
      groupByAssignment.set(`${step.commitment_vehicle_prefix}|${step.departure_at}`, group)
    }))
    return plan.assignments.map((assignment): PrescriptionRow => {
      const group = groupByAssignment.get(`${assignment.commitment_vehicle_prefix}|${assignment.departure_at}`)
      return { ...assignment, terminalId: plan.terminal_id, groupId: group?.group_id ?? '—', execution: group ? executionByKey.get(group.execution_key) : undefined }
    })
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
      execution: row.execution ? `Executado ${row.execution.executed_by}` : 'Pendente',
    }
    return (Object.keys(filters) as FilterKey[]).every((key) => matches(values[key], filters[key]))
  }).sort((first, second) => {
    if (Boolean(first.execution) !== Boolean(second.execution)) return first.execution ? 1 : -1
    return compareSortValues(rowSortValue(first, sort.key), rowSortValue(second, sort.key), sort.direction)
  }), [data, executionByKey, filters, showAll, sort])

  const confirmExecution = async () => {
    if (!confirmingGroup || !operatorName.trim()) return
    setConfirming(true); setConfirmationError(null)
    try {
      const execution = await confirmVehicleSwapExecution(confirmingGroup.execution_key, operatorName.trim())
      setExecutions((current) => [execution, ...current.filter((item) => item.execution_key !== execution.execution_key)])
      window.sessionStorage.setItem('gtfs-on-time-operator', operatorName.trim())
      setConfirmingGroup(null)
    } catch (cause) {
      setConfirmationError(cause instanceof Error ? cause.message : 'Não foi possível confirmar a execução')
    } finally { setConfirming(false) }
  }

  const changedCount = groups.reduce((total, group) => total + group.vehicle_count, 0)
  const pendingCount = groups.filter((group) => !executionByKey.has(group.execution_key)).length
  const setFilter = (key: FilterKey, value: string) => setFilters((current) => ({ ...current, [key]: value }))
  const filter = (key: FilterKey, label: string, placeholder?: string) => <ColumnFilter label={label} value={filters[key]} onChange={(value) => setFilter(key, value)} placeholder={placeholder} />
  const hasFilters = Object.values(filters).some(Boolean)
  const handleSort = (key: FilterKey) => setSort((current) => ({ key, direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc' }))
  const header = (key: FilterKey, label: string) => <SortableHeader columnKey={key} label={label} sort={sort} onSort={handleSort} />

  return (
    <section className="table-page prescription-page" aria-label="Prescrições de troca de veículos">
      <div className="prescription-summary">
        <article><span>Grupos pendentes</span><strong>{pendingCount}</strong><small>{changedCount} veículos envolvidos</small></article>
        <article><span>Tempo recuperável</span><strong>{formatMinutes(data?.total_saved_delay_seconds)}</strong><small>soma global dos terminais</small></article>
        <article><span>Terminais analisados</span><strong>{data?.terminal_count ?? '—'}</strong><small>{data?.eligible_vehicle_count ?? '—'} veículos elegíveis</small></article>
        <article className={`prescription-status ${data?.status ?? 'no_data'}`}><span>Estado do cálculo</span><strong>{data?.status === 'ready' ? 'Pronto' : data?.status === 'stale' ? 'Desatualizado' : 'Sem dados'}</strong><small>snapshot às {formatClock(data?.snapshot_generated_at)}</small></article>
      </div>

      <div className="prescription-view-tabs" role="tablist" aria-label="Visão das prescrições">
        <button role="tab" aria-selected={view === 'groups'} className={view === 'groups' ? 'active' : ''} onClick={() => setView('groups')}><Network size={16} /><span>Plano de trocas<small>{pendingCount} pendentes</small></span></button>
        <button role="tab" aria-selected={view === 'table'} className={view === 'table' ? 'active' : ''} onClick={() => setView('table')}><ListChecks size={16} /><span>Tabela completa<small>{rows.length} ações</small></span></button>
      </div>

      {error && <div className="inline-alert"><AlertCircle size={16} /> {error}</div>}

      {view === 'groups' && <div className="exchange-plan-list">
        {groups.map((group) => <ExchangeGroupCard key={group.execution_key} group={group} execution={executionByKey.get(group.execution_key)} scheduleByVehicle={scheduleByVehicle} onExecute={setConfirmingGroup} />)}
        {!groups.length && <div className="empty-prescriptions"><Sparkles size={26} /><strong>Nenhuma troca necessária agora</strong><span>O sistema continuará reavaliando os terminais.</span></div>}
      </div>}

      {view === 'table' && <>
        <div className="table-controls compact-controls">
          <label className="toggle-control"><input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} /> Mostrar alocações sem troca</label>
          <button className="clear-filters" onClick={() => setFilters(EMPTY_FILTERS)} disabled={!hasFilters}><FilterX size={15} /> Limpar filtros</button>
          <span className="table-result-count">{rows.length} ações</span>
        </div>
        <div className="data-table-shell">
          <table className="data-table prescription-table prescription-compact-table">
            <thead>
              <tr>
                <th>{header('action', 'Ação')}</th><th>{header('group', 'Grupo')}</th><th>{header('terminal', 'Terminal')}</th><th>{header('departure', 'Partida')}</th>
                <th>{header('originalVehicle', 'Programado')}</th><th>{header('assignedVehicle', 'Recomendado')}</th><th>{header('service', 'Linha / destino')}</th>
                <th>{header('originalArrival', 'Cheg. original')}</th><th>{header('assignedArrival', 'Cheg. recomendada')}</th><th>{header('margin', 'Folga')}</th>
                <th>{header('baselineDelay', 'Atraso orig.')}</th><th>{header('proposedDelay', 'Residual')}</th><th>{header('reduction', 'Redução')}</th>
                <th>{header('confidence', 'Conf.')}</th><th>{header('protection', 'Proteção')}</th><th>{header('execution', 'Execução')}</th>
              </tr>
              <tr className="column-filter-row">
                <th>{filter('action', 'ação')}</th><th>{filter('group', 'grupo', 'G01')}</th><th>{filter('terminal', 'terminal')}</th><th>{filter('departure', 'partida', 'HH:MM')}</th>
                <th>{filter('originalVehicle', 'veículo programado')}</th><th>{filter('assignedVehicle', 'veículo recomendado')}</th><th>{filter('service', 'linha ou destino')}</th>
                <th>{filter('originalArrival', 'chegada original', 'HH:MM')}</th><th>{filter('assignedArrival', 'chegada recomendada', 'HH:MM')}</th><th>{filter('margin', 'folga', '+min')}</th>
                <th>{filter('baselineDelay', 'atraso original', '+min')}</th><th>{filter('proposedDelay', 'atraso residual', '+min')}</th><th>{filter('reduction', 'redução', 'min')}</th>
                <th>{filter('confidence', 'confiança')}</th><th>{filter('protection', 'proteção')}</th><th>{filter('execution', 'execução')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => <tr key={`${row.terminalId}-${row.commitment_vehicle_prefix}-${row.departure_at}`} className={`${row.changed ? 'prescribed-row' : ''} ${row.execution ? 'executed-row' : ''}`}>
                <td><span className={`action-badge ${row.changed ? 'swap' : 'keep'}`}>{row.changed ? <ArrowRightLeft size={12} /> : <CheckCircle2 size={12} />}{row.changed ? 'Trocar' : 'Manter'}</span></td>
                <td><span className="group-chip">{row.groupId}</span></td><td><strong>{row.terminalId}</strong></td>
                <td><strong>{formatClock(row.departure_at)}</strong><small>{row.next_schedule_position ?? '—'}</small></td><td>{row.commitment_vehicle_prefix}</td>
                <td><strong className={row.changed ? 'recommended-vehicle' : ''}>{row.assigned_vehicle_prefix}</strong></td>
                <td className="compact-service-cell" title={`${row.next_line ?? '—'} · ${row.next_destination ?? '—'}`}><span>{row.next_line ?? '—'}</span><small>{row.next_destination ?? '—'}</small></td>
                <td>{formatClock(row.commitment_vehicle_arrival_at)}</td><td>{formatClock(row.assigned_vehicle_arrival_at)}</td>
                <td><span className={row.assigned_arrival_margin_seconds >= 0 ? 'saved-value' : 'delay-value baseline'}>{signedMinutes(row.assigned_arrival_margin_seconds)}</span></td>
                <td><span className="delay-value baseline">{signedMinutes(row.baseline_delay_seconds)}</span></td><td><span className="delay-value proposed">{signedMinutes(row.proposed_delay_seconds)}</span></td>
                <td><strong className="saved-value">{formatMinutes(row.delay_reduction_seconds)}</strong></td><td>{formatPercent(row.eta_reliability)}</td>
                <td>{row.protected ? <span className="protected-badge">Protegido</span> : 'Livre'}</td>
                <td>{row.execution ? <span className="executed-badge">Executado</span> : <span className="pending-badge">Pendente</span>}</td>
              </tr>)}
              {!rows.length && <tr><td colSpan={16} className="empty-table">Nenhuma ação corresponde aos filtros.</td></tr>}
            </tbody>
          </table>
        </div>
      </>}

      <footer className="table-footer">Cálculo global por terminal · janela protegida de {data?.protected_window_minutes ?? 10} minutos · avaliado às {formatClock(data?.evaluated_at)}</footer>

      {confirmingGroup && <div className="confirmation-overlay" role="presentation">
        <form className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmation-title" onSubmit={(event) => { event.preventDefault(); void confirmExecution() }}>
          <button type="button" className="icon-button close-button" onClick={() => setConfirmingGroup(null)} aria-label="Fechar confirmação"><X size={18} /></button>
          <CheckCircle2 size={28} className="confirmation-icon" />
          <h2 id="confirmation-title">Confirmar execução do grupo</h2>
          <p>Confirme somente após orientar todos os veículos do grupo <strong>{confirmingGroup.group_id}</strong>. A ação ficará registrada e irá para o fim da lista.</p>
          <label>Responsável pela confirmação<input autoFocus value={operatorName} onChange={(event) => setOperatorName(event.target.value)} placeholder="Nome ou matrícula" maxLength={100} required /></label>
          {confirmationError && <div className="inline-alert"><AlertCircle size={15} /> {confirmationError}</div>}
          <div className="confirmation-actions"><button type="button" onClick={() => setConfirmingGroup(null)}>Cancelar</button><button type="submit" disabled={confirming || !operatorName.trim()}>{confirming ? 'Confirmando…' : 'Confirmar execução'}</button></div>
        </form>
      </div>}
    </section>
  )
}
