import {
  AlertCircle, ArrowRight, ArrowRightLeft, CheckCircle2, Clock3, FilterX,
  ListChecks, Network, SearchCheck, ShieldCheck, Sparkles, UserCheck, X, XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import {
  getVehicleScheduleContexts,
  getVehicleSwapDecisions,
  getVehicleSwapPrescriptions,
  updateVehicleSwapDecision,
} from '../api'
import type {
  ExchangeGroup, PersistedSwapDecisionStatus, SwapAssignment, SwapDecision,
  SwapDecisionStatus, VehicleScheduleContext, VehicleScheduleContextList,
  VehicleSwapPrescription,
} from '../types'
import { formatClock, formatMinutes, formatPercent } from '../utils/format'
import { ColumnFilter } from './ColumnFilter'
import { compareSortValues, SortableHeader, type SortState } from './SortableHeader'

interface PrescriptionsTableProps { refreshToken: number }
interface PrescriptionRow extends SwapAssignment {
  terminalId: string
  groupId: string
  group?: ExchangeGroup
  decision?: SwapDecision
}
interface PendingDecision {
  group: ExchangeGroup
  status: PersistedSwapDecisionStatus
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
const STATUS_LABELS: Record<SwapDecisionStatus, string> = {
  new: 'Nova', in_analysis: 'Em análise', claimed: 'Assumida', executed: 'Executada',
  rejected: 'Recusada', expired: 'Expirada',
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

function deadlineLabel(departureAt: string, now: number) {
  const seconds = Math.round((Date.parse(departureAt) - now) / 1000)
  return seconds >= 0
    ? `${formatMinutes(seconds)} para decidir`
    : `Prazo vencido há ${formatMinutes(-seconds)}`
}

function effectiveStatus(
  group: ExchangeGroup,
  decision: SwapDecision | undefined,
  now: number,
): SwapDecisionStatus {
  if (decision?.status === 'executed' || decision?.status === 'rejected') return decision.status
  if (urgency(group) <= now) return 'expired'
  return decision?.status ?? 'new'
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
    execution: row.decision?.status,
  }
  return values[key]
}

function DecisionStatusBadge({ status }: { status: SwapDecisionStatus }) {
  const Icon = status === 'executed' ? CheckCircle2
    : status === 'rejected' ? XCircle
      : status === 'claimed' ? UserCheck
        : status === 'in_analysis' ? SearchCheck
          : Clock3
  return <span className={`decision-status-badge ${status}`}><Icon size={12} />{STATUS_LABELS[status]}</span>
}

function ExchangeGroupCard({
  group, decision, status, scheduleByVehicle, now, onDecision,
}: {
  group: ExchangeGroup
  decision?: SwapDecision
  status: SwapDecisionStatus
  scheduleByVehicle: Map<string, VehicleScheduleContext>
  now: number
  onDecision: (group: ExchangeGroup, status: PersistedSwapDecisionStatus) => void
}) {
  return (
    <article className={`exchange-plan-card decision-${status}`}>
      <header className="exchange-plan-header">
        <div>
          <span className="group-kicker">Grupo {group.group_id}</span>
          <strong>Terminal {group.terminal_id}</strong>
          <small>{group.vehicle_count} veículos · confirmação sempre conjunta</small>
        </div>
        <div className="group-status-stack">
          <span className={`urgency-badge ${urgency(group) < now ? 'late' : ''}`}><Clock3 size={13} /> {deadlineLabel(new Date(urgency(group)).toISOString(), now)}</span>
          <DecisionStatusBadge status={status} />
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
          const isDelayedTrip = step.baseline_delay_seconds > 0
          const deadlineExpired = Date.parse(step.departure_at) <= now
          return (
            <div className="group-action-row with-deadline" key={`${group.execution_key}-${step.commitment_vehicle_prefix}`}>
              <div className="action-order">{index + 1}</div>
              <div className="action-instruction">
                <span>Ação recomendada</span>
                <strong>Usar <b>{step.assigned_vehicle_prefix}</b> na viagem de {step.commitment_vehicle_prefix}</strong>
                <small>Linha {step.next_line ?? '—'} · {step.next_destination ?? 'Destino não informado'}</small>
              </div>
              <div className="action-time"><span>Chegada planejada</span><strong>{formatClock(assignedSchedule?.planned_end_at)}</strong></div>
              <div className="action-time forecast"><span>Chegada prevista</span><strong>{formatClock(step.assigned_vehicle_arrival_at)}</strong><small>original {formatClock(step.commitment_vehicle_arrival_at)}</small></div>
              <div className="action-time"><span>Saída planejada</span><strong>{formatClock(step.departure_at)}</strong><small>{step.next_schedule_position ?? '—'}</small></div>
              <div className="action-time"><span>Folga</span><strong className={step.assigned_arrival_margin_seconds >= 0 ? 'saved-value' : 'delay-value baseline'}>{signedMinutes(step.assigned_arrival_margin_seconds)}</strong><small>residual {signedMinutes(step.proposed_delay_seconds)}</small></div>
              <div className={`action-deadline ${deadlineExpired ? 'expired' : ''}`}><span>Prazo para decisão</span><strong>{isDelayedTrip ? deadlineLabel(step.departure_at, now) : 'Sem atraso original'}</strong><small>{isDelayedTrip ? `partida ${formatClock(step.departure_at)}` : 'não exige intervenção por atraso'}</small></div>
            </div>
          )
        })}
      </div>

      <footer className="exchange-plan-footer decision-footer">
        {decision && <span className="decision-audit"><ShieldCheck size={15} /> {STATUS_LABELS[decision.status]} por <strong>{decision.updated_by}</strong> às {formatClock(decision.updated_at)}{decision.rejection_reason ? ` · ${decision.rejection_reason}` : ''}</span>}
        {(status === 'new' || status === 'in_analysis' || status === 'claimed') && <div className="decision-actions">
          {status === 'new' && <button className="secondary" onClick={() => onDecision(group, 'in_analysis')}><SearchCheck size={15} /> Colocar em análise</button>}
          {(status === 'new' || status === 'in_analysis') && <button className="secondary" onClick={() => onDecision(group, 'claimed')}><UserCheck size={15} /> Assumir grupo</button>}
          <button className="reject" onClick={() => onDecision(group, 'rejected')}><XCircle size={15} /> Recusar grupo</button>
          <button onClick={() => onDecision(group, 'executed')}><CheckCircle2 size={15} /> Confirmar execução conjunta</button>
        </div>}
        {status === 'expired' && <span className="decision-audit"><Clock3 size={15} /> O prazo operacional expirou sem decisão final.</span>}
      </footer>
    </article>
  )
}

export function PrescriptionsTable({ refreshToken }: PrescriptionsTableProps) {
  const [data, setData] = useState<VehicleSwapPrescription | null>(null)
  const [decisions, setDecisions] = useState<SwapDecision[]>([])
  const [scheduleContexts, setScheduleContexts] = useState<VehicleScheduleContextList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<PrescriptionView>('groups')
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [sort, setSort] = useState<SortState<FilterKey>>({ key: 'departure', direction: 'asc' })
  const [showAll, setShowAll] = useState(false)
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null)
  const [operatorName, setOperatorName] = useState(() => window.sessionStorage.getItem('gtfs-on-time-operator') ?? '')
  const [rejectionReason, setRejectionReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [decisionError, setDecisionError] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      const results = await Promise.allSettled([
        getVehicleSwapPrescriptions(controller.signal),
        getVehicleSwapDecisions(controller.signal),
        getVehicleScheduleContexts(controller.signal),
      ])
      if (controller.signal.aborted) return
      const failures: string[] = []
      if (results[0].status === 'fulfilled') setData(results[0].value)
      else failures.push(results[0].reason instanceof Error ? results[0].reason.message : 'Falha nas prescrições')
      if (results[1].status === 'fulfilled') setDecisions(results[1].value.decisions)
      else failures.push(results[1].reason instanceof Error ? results[1].reason.message : 'Falha nas decisões')
      if (results[2].status === 'fulfilled') setScheduleContexts(results[2].value)
      else failures.push(results[2].reason instanceof Error ? results[2].reason.message : 'Falha nos horários')
      setError(failures.length ? failures.join(' · ') : null)
    }
    void load()
    const timer = window.setInterval(() => void load(), 30_000)
    return () => { window.clearInterval(timer); controller.abort() }
  }, [refreshToken])

  const decisionByKey = useMemo(() => new Map(decisions.map((item) => [item.execution_key, item])), [decisions])
  const scheduleByVehicle = useMemo(() => new Map((scheduleContexts?.vehicles ?? []).map((item) => [item.vehicle_prefix, item])), [scheduleContexts])
  const groups = useMemo(() => (data?.plans ?? []).flatMap((plan) => plan.exchange_groups).sort((first, second) => {
    const statusOrder: Record<SwapDecisionStatus, number> = { claimed: 0, in_analysis: 1, new: 2, expired: 3, rejected: 4, executed: 5 }
    const firstStatus = effectiveStatus(first, decisionByKey.get(first.execution_key), now)
    const secondStatus = effectiveStatus(second, decisionByKey.get(second.execution_key), now)
    return statusOrder[firstStatus] - statusOrder[secondStatus] || urgency(first) - urgency(second) || second.saved_delay_seconds - first.saved_delay_seconds
  }), [data, decisionByKey, now])

  const rows = useMemo(() => (data?.plans ?? []).flatMap((plan) => {
    const groupByAssignment = new Map<string, ExchangeGroup>()
    plan.exchange_groups.forEach((group) => group.steps.forEach((step) => groupByAssignment.set(`${step.commitment_vehicle_prefix}|${step.departure_at}`, group)))
    return plan.assignments.map((assignment): PrescriptionRow => {
      const group = groupByAssignment.get(`${assignment.commitment_vehicle_prefix}|${assignment.departure_at}`)
      return { ...assignment, terminalId: plan.terminal_id, groupId: group?.group_id ?? '—', group, decision: group ? decisionByKey.get(group.execution_key) : undefined }
    })
  }).filter((row) => showAll || row.changed).filter((row) => {
    const status = row.group ? effectiveStatus(row.group, row.decision, now) : 'new'
    const values: Record<FilterKey, unknown> = {
      action: row.changed ? 'Trocar' : 'Manter', group: row.groupId, terminal: row.terminalId,
      departure: `${formatClock(row.departure_at)} ${deadlineLabel(row.departure_at, now)}`, originalVehicle: row.commitment_vehicle_prefix,
      assignedVehicle: row.assigned_vehicle_prefix,
      service: `${row.next_line ?? ''} ${row.next_direction ?? ''} ${row.next_destination ?? ''} ${row.next_schedule_position ?? ''}`,
      originalArrival: formatClock(row.commitment_vehicle_arrival_at), assignedArrival: formatClock(row.assigned_vehicle_arrival_at),
      margin: signedMinutes(row.assigned_arrival_margin_seconds), baselineDelay: signedMinutes(row.baseline_delay_seconds),
      proposedDelay: signedMinutes(row.proposed_delay_seconds), reduction: formatMinutes(row.delay_reduction_seconds),
      confidence: formatPercent(row.eta_reliability), protection: row.protected ? 'Protegido' : 'Livre',
      execution: STATUS_LABELS[status],
    }
    return (Object.keys(filters) as FilterKey[]).every((key) => matches(values[key], filters[key]))
  }).sort((first, second) => {
    const firstFinal = first.decision?.status === 'executed' || first.decision?.status === 'rejected'
    const secondFinal = second.decision?.status === 'executed' || second.decision?.status === 'rejected'
    if (firstFinal !== secondFinal) return firstFinal ? 1 : -1
    return compareSortValues(rowSortValue(first, sort.key), rowSortValue(second, sort.key), sort.direction)
  }), [data, decisionByKey, filters, now, showAll, sort])

  const saveDecision = async () => {
    if (!pendingDecision || !operatorName.trim()) return
    if (pendingDecision.status === 'rejected' && !rejectionReason.trim()) return
    setSaving(true); setDecisionError(null)
    try {
      const decision = await updateVehicleSwapDecision(
        pendingDecision.group.execution_key,
        pendingDecision.status,
        operatorName.trim(),
        pendingDecision.status === 'rejected' ? rejectionReason.trim() : undefined,
      )
      setDecisions((current) => [decision, ...current.filter((item) => item.execution_key !== decision.execution_key)])
      window.sessionStorage.setItem('gtfs-on-time-operator', operatorName.trim())
      setPendingDecision(null); setRejectionReason('')
    } catch (cause) {
      setDecisionError(cause instanceof Error ? cause.message : 'Não foi possível registrar a decisão')
    } finally { setSaving(false) }
  }

  const openDecision = (group: ExchangeGroup, status: PersistedSwapDecisionStatus) => {
    setPendingDecision({ group, status }); setRejectionReason(''); setDecisionError(null)
  }
  const pendingCount = groups.filter((group) => !['executed', 'rejected', 'expired'].includes(effectiveStatus(group, decisionByKey.get(group.execution_key), now))).length
  const changedCount = groups.reduce((total, group) => total + group.vehicle_count, 0)
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
        {groups.map((group) => <ExchangeGroupCard key={group.execution_key} group={group} decision={decisionByKey.get(group.execution_key)} status={effectiveStatus(group, decisionByKey.get(group.execution_key), now)} scheduleByVehicle={scheduleByVehicle} now={now} onDecision={openDecision} />)}
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
            <thead><tr>
              <th>{header('action', 'Ação')}</th><th>{header('group', 'Grupo')}</th><th>{header('terminal', 'Terminal')}</th><th>{header('departure', 'Partida / prazo')}</th>
              <th>{header('originalVehicle', 'Programado')}</th><th>{header('assignedVehicle', 'Recomendado')}</th><th>{header('service', 'Linha / destino')}</th>
              <th>{header('originalArrival', 'Cheg. original')}</th><th>{header('assignedArrival', 'Cheg. recomendada')}</th><th>{header('margin', 'Folga')}</th>
              <th>{header('baselineDelay', 'Atraso orig.')}</th><th>{header('proposedDelay', 'Residual')}</th><th>{header('reduction', 'Redução')}</th>
              <th>{header('confidence', 'Conf.')}</th><th>{header('protection', 'Proteção')}</th><th>{header('execution', 'Estado')}</th>
            </tr><tr className="column-filter-row">
              <th>{filter('action', 'ação')}</th><th>{filter('group', 'grupo', 'G01')}</th><th>{filter('terminal', 'terminal')}</th><th>{filter('departure', 'partida ou prazo', 'HH:MM')}</th>
              <th>{filter('originalVehicle', 'veículo programado')}</th><th>{filter('assignedVehicle', 'veículo recomendado')}</th><th>{filter('service', 'linha ou destino')}</th>
              <th>{filter('originalArrival', 'chegada original', 'HH:MM')}</th><th>{filter('assignedArrival', 'chegada recomendada', 'HH:MM')}</th><th>{filter('margin', 'folga', '+min')}</th>
              <th>{filter('baselineDelay', 'atraso original', '+min')}</th><th>{filter('proposedDelay', 'atraso residual', '+min')}</th><th>{filter('reduction', 'redução', 'min')}</th>
              <th>{filter('confidence', 'confiança')}</th><th>{filter('protection', 'proteção')}</th><th>{filter('execution', 'estado')}</th>
            </tr></thead>
            <tbody>
              {rows.map((row) => {
                const status = row.group ? effectiveStatus(row.group, row.decision, now) : 'new'
                return <tr key={`${row.terminalId}-${row.commitment_vehicle_prefix}-${row.departure_at}`} className={`${row.changed ? 'prescribed-row' : ''} decision-row-${status}`}>
                  <td><span className={`action-badge ${row.changed ? 'swap' : 'keep'}`}>{row.changed ? <ArrowRightLeft size={12} /> : <CheckCircle2 size={12} />}{row.changed ? 'Trocar' : 'Manter'}</span></td>
                  <td><span className="group-chip">{row.groupId}</span></td><td><strong>{row.terminalId}</strong></td>
                  <td><strong>{formatClock(row.departure_at)}</strong><small className={Date.parse(row.departure_at) <= now ? 'deadline-expired' : ''}>{deadlineLabel(row.departure_at, now)}</small></td><td>{row.commitment_vehicle_prefix}</td>
                  <td><strong className={row.changed ? 'recommended-vehicle' : ''}>{row.assigned_vehicle_prefix}</strong></td>
                  <td className="compact-service-cell" title={`${row.next_line ?? '—'} · ${row.next_destination ?? '—'}`}><span>{row.next_line ?? '—'}</span><small>{row.next_destination ?? '—'}</small></td>
                  <td>{formatClock(row.commitment_vehicle_arrival_at)}</td><td>{formatClock(row.assigned_vehicle_arrival_at)}</td>
                  <td><span className={row.assigned_arrival_margin_seconds >= 0 ? 'saved-value' : 'delay-value baseline'}>{signedMinutes(row.assigned_arrival_margin_seconds)}</span></td>
                  <td><span className="delay-value baseline">{signedMinutes(row.baseline_delay_seconds)}</span></td><td><span className="delay-value proposed">{signedMinutes(row.proposed_delay_seconds)}</span></td>
                  <td><strong className="saved-value">{formatMinutes(row.delay_reduction_seconds)}</strong></td><td>{formatPercent(row.eta_reliability)}</td>
                  <td>{row.protected ? <span className="protected-badge">Protegido</span> : 'Livre'}</td><td><DecisionStatusBadge status={status} /></td>
                </tr>
              })}
              {!rows.length && <tr><td colSpan={16} className="empty-table">Nenhuma ação corresponde aos filtros.</td></tr>}
            </tbody>
          </table>
        </div>
      </>}

      <footer className="table-footer">Cálculo global por terminal · janela protegida de {data?.protected_window_minutes ?? 10} minutos · avaliado às {formatClock(data?.evaluated_at)}</footer>

      {pendingDecision && <div className="confirmation-overlay" role="presentation">
        <form className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="decision-title" onSubmit={(event) => { event.preventDefault(); void saveDecision() }}>
          <button type="button" className="icon-button close-button" onClick={() => setPendingDecision(null)} aria-label="Fechar decisão"><X size={18} /></button>
          {pendingDecision.status === 'rejected' ? <XCircle size={28} className="confirmation-icon reject" /> : <CheckCircle2 size={28} className="confirmation-icon" />}
          <h2 id="decision-title">{STATUS_LABELS[pendingDecision.status]} — grupo {pendingDecision.group.group_id}</h2>
          <p>{pendingDecision.status === 'executed' ? 'Confirme somente após orientar todos os veículos. A execução será registrada conjuntamente para o grupo fechado.' : pendingDecision.status === 'rejected' ? 'A recusa será aplicada ao grupo completo e o motivo ficará gravado localmente para auditoria.' : 'A alteração de estado vale para todo o grupo fechado.'}</p>
          <label>Responsável<input autoFocus value={operatorName} onChange={(event) => setOperatorName(event.target.value)} placeholder="Nome ou matrícula" maxLength={100} required /></label>
          {pendingDecision.status === 'rejected' && <label>Motivo da recusa<textarea value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} placeholder="Informe por que o grupo não será executado" maxLength={500} required /></label>}
          {decisionError && <div className="inline-alert"><AlertCircle size={15} /> {decisionError}</div>}
          <div className="confirmation-actions"><button type="button" onClick={() => setPendingDecision(null)}>Cancelar</button><button type="submit" className={pendingDecision.status === 'rejected' ? 'reject' : ''} disabled={saving || !operatorName.trim() || (pendingDecision.status === 'rejected' && !rejectionReason.trim())}>{saving ? 'Gravando…' : `Confirmar: ${STATUS_LABELS[pendingDecision.status]}`}</button></div>
        </form>
      </div>}
    </section>
  )
}
