import { AlertCircle, ArrowRightLeft, CheckCircle2, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { getVehicleSwapPrescriptions } from '../api'
import type { SwapAssignment, VehicleSwapPrescription } from '../types'
import { formatClock, formatMinutes, formatPercent } from '../utils/format'

interface PrescriptionsTableProps {
  refreshToken: number
}

interface PrescriptionRow extends SwapAssignment {
  terminalId: string
}

function signedMinutes(seconds: number) {
  const minutes = Math.round(seconds / 60)
  if (minutes === 0) return '0 min'
  return `${minutes > 0 ? '+' : ''}${minutes} min`
}

export function PrescriptionsTable({ refreshToken }: PrescriptionsTableProps) {
  const [data, setData] = useState<VehicleSwapPrescription | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try {
        setData(await getVehicleSwapPrescriptions(controller.signal))
        setError(null)
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setError(cause instanceof Error ? cause.message : 'Falha ao carregar prescrições')
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), 30_000)
    return () => {
      window.clearInterval(timer)
      controller.abort()
    }
  }, [refreshToken])

  const rows = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('pt-BR')
    return (data?.plans ?? [])
      .flatMap((plan) =>
        plan.assignments.map((assignment) => ({ ...assignment, terminalId: plan.terminal_id })),
      )
      .filter((assignment) => showAll || assignment.changed)
      .filter((assignment) =>
        !normalized ||
        [
          assignment.terminalId,
          assignment.commitment_vehicle_prefix,
          assignment.assigned_vehicle_prefix,
          assignment.next_line,
          assignment.next_destination,
        ]
          .filter(Boolean)
          .some((value) => value!.toLocaleLowerCase('pt-BR').includes(normalized)),
      )
      .sort((a, b) => b.delay_reduction_seconds - a.delay_reduction_seconds)
  }, [data, query, showAll])

  const changedCount = (data?.plans ?? []).reduce(
    (total, plan) => total + plan.assignments.filter((assignment) => assignment.changed).length,
    0,
  )

  return (
    <section className="table-page" aria-label="Prescrições de troca de veículos">
      <div className="prescription-summary">
        <article><span>Trocas recomendadas</span><strong>{changedCount}</strong><small>ações com redução de atraso</small></article>
        <article><span>Tempo recuperado</span><strong>{formatMinutes(data?.total_saved_delay_seconds)}</strong><small>soma global dos terminais</small></article>
        <article><span>Terminais analisados</span><strong>{data?.terminal_count ?? '—'}</strong><small>{data?.eligible_vehicle_count ?? '—'} veículos elegíveis</small></article>
        <article className={`prescription-status ${data?.status ?? 'no_data'}`}><span>Estado do cálculo</span><strong>{data?.status === 'ready' ? 'Pronto' : data?.status === 'stale' ? 'Desatualizado' : 'Sem dados'}</strong><small>snapshot às {formatClock(data?.snapshot_generated_at)}</small></article>
      </div>

      <div className="table-controls">
        <label className="table-search">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Terminal, veículo, linha ou destino"
            aria-label="Filtrar prescrições"
          />
        </label>
        <label className="toggle-control">
          <input type="checkbox" checked={showAll} onChange={(event) => setShowAll(event.target.checked)} />
          Mostrar alocações sem troca
        </label>
        <span className="table-result-count">{rows.length} ações</span>
      </div>

      {error && <div className="inline-alert"><AlertCircle size={16} /> {error}</div>}

      <div className="data-table-shell">
        <table className="data-table prescription-table">
          <thead>
            <tr>
              <th>Ação</th>
              <th>Terminal</th>
              <th>Partida</th>
              <th>Veículo programado</th>
              <th>Veículo recomendado</th>
              <th>Linha / destino</th>
              <th>Chegada do recomendado</th>
              <th>Atraso original</th>
              <th>Atraso residual</th>
              <th>Redução</th>
              <th>Confiança ETA</th>
              <th>Proteção</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.terminalId}-${row.commitment_vehicle_prefix}-${row.departure_at}`} className={row.changed ? 'prescribed-row' : ''}>
                <td>
                  <span className={`action-badge ${row.changed ? 'swap' : 'keep'}`}>
                    {row.changed ? <ArrowRightLeft size={13} /> : <CheckCircle2 size={13} />}
                    {row.changed ? 'Trocar' : 'Manter'}
                  </span>
                </td>
                <td><strong>{row.terminalId}</strong></td>
                <td><strong>{formatClock(row.departure_at)}</strong><small>{row.next_schedule_position ?? '—'}</small></td>
                <td>{row.commitment_vehicle_prefix}</td>
                <td><strong className={row.changed ? 'recommended-vehicle' : ''}>{row.assigned_vehicle_prefix}</strong></td>
                <td className="wide-cell"><span>{row.next_line ?? '—'} · {row.next_direction ?? '—'}</span><small>{row.next_destination ?? '—'}</small></td>
                <td>{formatClock(row.assigned_vehicle_arrival_at)}</td>
                <td><span className="delay-value baseline">{signedMinutes(row.baseline_delay_seconds)}</span></td>
                <td><span className="delay-value proposed">{signedMinutes(row.proposed_delay_seconds)}</span></td>
                <td><strong className="saved-value">{formatMinutes(row.delay_reduction_seconds)}</strong></td>
                <td>{formatPercent(row.eta_reliability)}</td>
                <td>{row.protected ? <span className="protected-badge">Protegido</span> : '—'}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={12} className="empty-table">Nenhuma troca recomendada no snapshot atual.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <footer className="table-footer">
        Cálculo global por terminal · janela protegida de {data?.protected_window_minutes ?? 10} minutos · avaliado às {formatClock(data?.evaluated_at)}
      </footer>
    </section>
  )
}
