import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  Bell,
  BusFront,
  ChevronRight,
  Clock3,
  LayoutDashboard,
  MapPinned,
  Menu,
  RefreshCw,
  Search,
  Sparkles,
  TableProperties,
} from 'lucide-react'

import {
  ApiError,
  getTripGeometry,
  getVehicleEta,
  getVehicleEtaSnapshots,
  getVehicleScheduleContexts,
} from './api'
import { FleetTable } from './components/FleetTable'
import { PrescriptionsTable } from './components/PrescriptionsTable'
import { VehicleDetails } from './components/VehicleDetails'
import { useFleetPositions } from './hooks/useFleetPositions'
import type {
  ProjectedVehiclePosition,
  TripGeometry,
  VehicleEta,
  VehicleEtaSnapshotList,
  VehicleScheduleContextList,
} from './types'
import { formatClock } from './utils/format'
import { buildVehicleOperationalStatus } from './utils/operationalStatus'

const OperationsMap = lazy(() =>
  import('./components/OperationsMap').then((module) => ({ default: module.OperationsMap })),
)

type ActiveView = 'overview' | 'map' | 'fleet' | 'prescriptions'

function App() {
  const { data, error, loading, refresh } = useFleetPositions()
  const [selectedPrefix, setSelectedPrefix] = useState<string | null>(() =>
    window.sessionStorage.getItem('gtfs-on-time-selected-vehicle'),
  )
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeView, setActiveView] = useState<ActiveView>('map')
  const [viewRefreshToken, setViewRefreshToken] = useState(0)
  const selectedVehicleSnapshot = useRef<ProjectedVehiclePosition | null>(null)
  const [geometry, setGeometry] = useState<TripGeometry | null>(null)
  const [eta, setEta] = useState<VehicleEta | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [etaSnapshots, setEtaSnapshots] = useState<VehicleEtaSnapshotList | null>(null)
  const [scheduleContexts, setScheduleContexts] = useState<VehicleScheduleContextList | null>(null)

  const vehicles = data?.vehicles ?? []
  const liveSelectedVehicle = useMemo(
    () => vehicles.find((vehicle) => vehicle.vehicle_prefix === selectedPrefix) ?? null,
    [selectedPrefix, vehicles],
  )
  if (!selectedPrefix) {
    selectedVehicleSnapshot.current = null
  } else if (liveSelectedVehicle) {
    selectedVehicleSnapshot.current = liveSelectedVehicle
  } else if (selectedVehicleSnapshot.current?.vehicle_prefix !== selectedPrefix) {
    selectedVehicleSnapshot.current = null
  }
  const selectedVehicle = liveSelectedVehicle ?? selectedVehicleSnapshot.current
  const etaByVehicle = useMemo(
    () => new Map((etaSnapshots?.vehicles ?? []).map((item) => [item.vehicle_prefix, item])),
    [etaSnapshots],
  )
  const scheduleByVehicle = useMemo(
    () => new Map((scheduleContexts?.vehicles ?? []).map((item) => [item.vehicle_prefix, item])),
    [scheduleContexts],
  )
  const operationalStatusByVehicle = useMemo(
    () => new Map(vehicles.map((vehicle) => [
      vehicle.vehicle_prefix,
      buildVehicleOperationalStatus(
        etaByVehicle.get(vehicle.vehicle_prefix),
        scheduleByVehicle.get(vehicle.vehicle_prefix),
      ),
    ])),
    [etaByVehicle, scheduleByVehicle, vehicles],
  )
  const selectedOperationalStatus = selectedVehicle
    ? operationalStatusByVehicle.get(selectedVehicle.vehicle_prefix)
    : undefined
  const selectedSchedule = selectedVehicle
    ? scheduleByVehicle.get(selectedVehicle.vehicle_prefix) ?? null
    : null
  const searchResults = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase('pt-BR')
    if (!normalized) return []
    return vehicles
      .filter((vehicle) =>
        [vehicle.vehicle_prefix, vehicle.route_short_name, vehicle.current_line, vehicle.headsign]
          .filter(Boolean)
          .some((value) => value!.toLocaleLowerCase('pt-BR').includes(normalized)),
      )
      .slice(0, 8)
  }, [query, vehicles])

  useEffect(() => {
    const controller = new AbortController()
    const loadOperationalReferences = async () => {
      const [etaResult, scheduleResult] = await Promise.allSettled([
        getVehicleEtaSnapshots(controller.signal),
        getVehicleScheduleContexts(controller.signal),
      ])
      if (controller.signal.aborted) return
      if (etaResult.status === 'fulfilled') setEtaSnapshots(etaResult.value)
      if (scheduleResult.status === 'fulfilled') setScheduleContexts(scheduleResult.value)
    }
    void loadOperationalReferences()
    const timer = window.setInterval(() => void loadOperationalReferences(), 30_000)
    return () => {
      window.clearInterval(timer)
      controller.abort()
    }
  }, [viewRefreshToken])

  useEffect(() => {
    if (!selectedVehicle) {
      setGeometry(null)
      setEta(null)
      setDetailError(null)
      return
    }
    const controller = new AbortController()
    setDetailLoading(true)
    setDetailError(null)
    Promise.allSettled([
      getTripGeometry(selectedVehicle.trip_id, controller.signal),
      getVehicleEta(selectedVehicle.vehicle_prefix, controller.signal),
    ]).then(([geometryResult, etaResult]) => {
      if (controller.signal.aborted) return
      if (geometryResult.status === 'fulfilled') setGeometry(geometryResult.value)
      else setGeometry(null)
      if (etaResult.status === 'fulfilled') setEta(etaResult.value)
      else setEta(null)

      const failures = [geometryResult, etaResult].filter(
        (result) => result.status === 'rejected',
      ) as PromiseRejectedResult[]
      if (failures.length) {
        const first = failures[0].reason
        setDetailError(
          first instanceof ApiError && first.status === 409
            ? 'ETA temporariamente indisponível para este veículo.'
            : first instanceof Error
              ? first.message
              : 'Não foi possível carregar todos os detalhes.',
        )
      }
      setDetailLoading(false)
    })
    return () => controller.abort()
  }, [selectedVehicle?.trip_id, selectedVehicle?.vehicle_prefix])

  const validCount = vehicles.filter((vehicle) => vehicle.projection_quality === 'valid').length
  const criticalDelayCount = [...operationalStatusByVehicle.values()].filter(
    (status) => status.status === 'delayed',
  ).length

  const selectVehicle = (prefix: string) => {
    setSelectedPrefix(prefix)
    window.sessionStorage.setItem('gtfs-on-time-selected-vehicle', prefix)
    setQuery('')
  }

  const clearSelectedVehicle = () => {
    setSelectedPrefix(null)
    window.sessionStorage.removeItem('gtfs-on-time-selected-vehicle')
  }

  const openVehicleOnMap = (prefix: string) => {
    selectVehicle(prefix)
    setActiveView('map')
  }

  const refreshCurrentView = () => {
    void refresh()
    setViewRefreshToken((token) => token + 1)
  }

  const viewCopy: Record<ActiveView, { eyebrow: string; title: string; accent: string }> = {
    overview: { eyebrow: 'Centro de controle operacional', title: 'Visão', accent: 'geral' },
    map: { eyebrow: 'Monitoramento operacional', title: 'Frota', accent: 'em tempo real' },
    fleet: { eyebrow: 'Acompanhamento veículo a veículo', title: 'Tabela', accent: 'da frota' },
    prescriptions: { eyebrow: 'Otimização global por terminal', title: 'Ações', accent: 'prescritivas' },
  }
  const currentViewCopy = viewCopy[activeView]

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="topbar-menu"
          aria-label={sidebarOpen ? 'Fechar menu' : 'Abrir menu'}
          aria-expanded={sidebarOpen}
          aria-controls="primary-navigation"
          onClick={() => setSidebarOpen((open) => !open)}
        >
          <Menu size={22} />
        </button>
        <div className="brand-lockup">
          <span className="brand-wordmark">Urbi</span>
          <span className="brand-divider" />
          <span className="brand-product">Operação em tempo real</span>
        </div>
        <div className="topbar-context">
          <span>CCO</span><ChevronRight size={16} /><strong>Monitoramento da frota</strong>
        </div>
        <div className="topbar-status">
          <span className="live-dot" /> Dados atualizados às {formatClock(data?.generated_at)}
        </div>
        <button className="topbar-icon" aria-label="Notificações"><Bell size={19} /></button>
        <div className="user-chip">CCO</div>
      </header>

      <nav
        id="primary-navigation"
        className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}
        aria-label="Navegação principal"
        aria-hidden={!sidebarOpen}
        inert={!sidebarOpen}
      >
        <button className={`sidebar-button ${activeView === 'overview' ? 'active' : ''}`} onClick={() => setActiveView('overview')}><LayoutDashboard size={20} /><span>Visão geral</span></button>
        <button className={`sidebar-button ${activeView === 'map' ? 'active' : ''}`} onClick={() => setActiveView('map')}><MapPinned size={20} /><span>Mapa</span></button>
        <button className={`sidebar-button ${activeView === 'fleet' ? 'active' : ''}`} onClick={() => setActiveView('fleet')}><TableProperties size={20} /><span>Frota</span></button>
        <button className={`sidebar-button ${activeView === 'prescriptions' ? 'active' : ''}`} onClick={() => setActiveView('prescriptions')}><Sparkles size={20} /><span>Prescrições</span></button>
      </nav>

      <main className={`workspace ${sidebarOpen ? '' : 'sidebar-closed'}`}>
        <div className="workspace-heading">
          <div>
            <span className="eyebrow">{currentViewCopy.eyebrow}</span>
            <h1><span>{currentViewCopy.title}</span> {currentViewCopy.accent}</h1>
          </div>
          <button className="refresh-button" onClick={refreshCurrentView} disabled={loading && activeView === 'map'}>
            <RefreshCw size={17} className={loading ? 'spin' : ''} /> Atualizar agora
          </button>
        </div>

        {(activeView === 'overview' || activeView === 'map') && <section className="kpi-strip" aria-label="Indicadores da frota">
          <article className="kpi-card blue">
            <div className="kpi-icon"><BusFront size={21} /></div>
            <div><span>Veículos projetados</span><strong>{data?.count ?? '—'}</strong><small>map matching resolvido</small></div>
          </article>
          <article className="kpi-card green">
            <div className="kpi-icon"><MapPinned size={21} /></div>
            <div><span>Projeções válidas</span><strong>{validCount}</strong><small>{vehicles.length ? Math.round((validCount / vehicles.length) * 100) : 0}% da visão atual</small></div>
          </article>
          <article className="kpi-card orange">
            <div className="kpi-icon"><Clock3 size={21} /></div>
            <div><span>Atrasos críticos</span><strong>{criticalDelayCount}</strong><small>ETA acima de 10 minutos</small></div>
          </article>
          <article className={`kpi-card ${error ? 'red' : 'navy'}`}>
            <div className="kpi-icon">{error ? <AlertCircle size={21} /> : <span className="signal-bars">▮▮▮</span>}</div>
            <div><span>Status da atualização</span><strong className="status-copy">{error ? 'Atenção' : 'Operacional'}</strong><small>{error ?? 'ciclo de 10 segundos'}</small></div>
          </article>
        </section>}

        {activeView === 'overview' && (
          <section className="overview-grid">
            <button onClick={() => setActiveView('map')}>
              <MapPinned size={25} /><span><strong>Mapa operacional</strong><small>Acompanhar posições, rotas e ETAs em tempo real</small></span><ChevronRight size={19} />
            </button>
            <button onClick={() => setActiveView('fleet')}>
              <TableProperties size={25} /><span><strong>Tabela da frota</strong><small>Comparar situação e previsão de cada veículo</small></span><ChevronRight size={19} />
            </button>
            <button onClick={() => setActiveView('prescriptions')}>
              <Sparkles size={25} /><span><strong>Prescrições do CCO</strong><small>Priorizar trocas que reduzem o atraso global</small></span><ChevronRight size={19} />
            </button>
          </section>
        )}

        {activeView === 'map' && <section className="map-card">
          <div className="map-toolbar">
            <div className="vehicle-search">
              <Search size={18} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Buscar veículo, linha ou destino"
                aria-label="Buscar veículo"
              />
              {searchResults.length > 0 && (
                <div className="search-results">
                  {searchResults.map((vehicle) => (
                    <button key={vehicle.vehicle_prefix} onClick={() => selectVehicle(vehicle.vehicle_prefix)}>
                      <span className="result-bus"><BusFront size={16} /></span>
                      <span><strong>{vehicle.vehicle_prefix}</strong><small>Linha {vehicle.route_short_name ?? vehicle.current_line ?? '—'}</small></span>
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="map-legend">
              <span><i className="legend-dot on-time" /> No horário</span>
              <span><i className="legend-dot warning" /> Até 10 min</span>
              <span><i className="legend-dot delayed" /> Acima de 10 min</span>
              <span><i className="legend-dot reduced" /> Sem referência</span>
              <span><i className="legend-line current" /> Trecho atual</span>
            </div>
          </div>

          <Suspense fallback={<div className="map-loading"><RefreshCw className="spin" /> Carregando mapa…</div>}>
            <OperationsMap
              vehicles={vehicles}
              selectedVehicle={selectedVehicle}
              tripGeometry={geometry}
              operationalStatusByVehicle={operationalStatusByVehicle}
              onSelectVehicle={selectVehicle}
            />
          </Suspense>

          {loading && !data && <div className="map-loading"><RefreshCw className="spin" /> Carregando frota…</div>}
          {selectedVehicle && (
            <VehicleDetails
              vehicle={selectedVehicle}
              geometry={geometry}
              eta={eta}
              schedule={selectedSchedule}
              operationalStatus={selectedOperationalStatus}
              loading={detailLoading}
              error={detailError}
              onClose={clearSelectedVehicle}
            />
          )}
        </section>}

        {activeView === 'fleet' && (
          <FleetTable
            positions={vehicles}
            refreshToken={viewRefreshToken}
            onOpenVehicle={openVehicleOnMap}
          />
        )}

        {activeView === 'prescriptions' && (
          <PrescriptionsTable refreshToken={viewRefreshToken} />
        )}
      </main>
    </div>
  )
}

export default App
