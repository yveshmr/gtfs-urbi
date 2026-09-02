import { useEffect, useMemo, useRef, useState } from 'react'
import type { FeatureCollection, LineString } from 'geojson'
import {
  GeoJSONSource, LngLatBounds, Map as MapLibreMap, NavigationControl,
  setWorkerUrl, type FilterSpecification, type MapLayerMouseEvent, type SourceSpecification, type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

import { getSegmentSpeeds } from '../api'
import type { SegmentSpeedMapItem, SegmentSpeedMapResponse } from '../types'
import { formatClock, formatDistance, formatMinutes, formatPercent } from '../utils/format'

setWorkerUrl(workerUrl)

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }
const OMT_NEUTRAL_STYLE = 'https://tiles.openfreemap.org/styles/positron'
const OPENFREEMAP_DARK_STYLE = 'https://tiles.openfreemap.org/styles/dark'
const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, attribution: '&copy; OpenStreetMap contributors' },
    dark: { type: 'raster', tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'], tileSize: 256, attribution: '&copy; OpenStreetMap contributors &copy; CARTO' },
    satellite: { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, attribution: 'Tiles &copy; Esri and imagery providers' },
    segments: { type: 'geojson', data: EMPTY },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#ECF1F5' } },
    { id: 'osm', type: 'raster', source: 'osm' },
    { id: 'dark', type: 'raster', source: 'dark', layout: { visibility: 'none' } },
    { id: 'satellite', type: 'raster', source: 'satellite', layout: { visibility: 'none' } },
    { id: 'segments-shadow', type: 'line', source: 'segments', paint: { 'line-color': '#003B5C', 'line-width': 7, 'line-opacity': .18 } },
    { id: 'segments-line', type: 'line', source: 'segments', paint: {
      'line-color': ['match', ['get', 'source'], 'gtfs_planned', '#9CA3AF',
        ['step', ['get', 'speed'], '#EB5757', 10.0001, '#F2994A', 20.0001, '#F2C94C', 30.0001, '#2EB67D']],
      'line-width': 5, 'line-opacity': .92,
    } },
    { id: 'selected-segment-line', type: 'line', source: 'segments', filter: ['==', ['get', 'id'], ''], paint: { 'line-color': '#FFFFFF', 'line-width': 11, 'line-opacity': .95 } },
    { id: 'selected-segment-core', type: 'line', source: 'segments', filter: ['==', ['get', 'id'], ''], paint: { 'line-color': '#003B5C', 'line-width': 7, 'line-opacity': 1 } },
  ],
}

function addSegmentLayers(map: MapLibreMap) {
  if (!map.getSource('segments')) map.addSource('segments', structuredClone(STYLE.sources.segments as SourceSpecification))
  for (const id of ['segments-shadow', 'segments-line', 'selected-segment-line', 'selected-segment-core']) {
    if (!map.getLayer(id)) {
      const layer = STYLE.layers.find((candidate) => candidate.id === id)
      if (layer) map.addLayer(structuredClone(layer))
    }
  }
}

function collection(segments: SegmentSpeedMapItem[], showPlanned: boolean): FeatureCollection<LineString> {
  return { type: 'FeatureCollection', features: segments
    .filter((segment) => showPlanned || segment.source !== 'gtfs_planned')
    .map((segment) => ({
      type: 'Feature', id: segment.segment_id, geometry: segment.geometry,
      properties: { id: segment.segment_id, source: segment.source, speed: segment.speed_kmh },
    })) }
}

export function SegmentSpeedMap({ refreshToken }: { refreshToken: number }) {
  const container = useRef<HTMLDivElement | null>(null)
  const map = useRef<MapLibreMap | null>(null)
  const styleFamily = useRef<'neutral' | 'dark' | 'satellite'>('neutral')
  const fitted = useRef(false)
  const [data, setData] = useState<SegmentSpeedMapResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showPlanned, setShowPlanned] = useState(true)
  const [basemap, setBasemap] = useState<'neutral' | 'dark' | 'satellite'>('neutral')
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selected = useMemo(() => data?.segments.find((item) => item.segment_id === selectedId) ?? null, [data, selectedId])

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try { setData(await getSegmentSpeeds(controller.signal)); setError(null) }
      catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause instanceof Error ? cause.message : 'Falha ao carregar trechos') }
    }
    void load()
    const timer = window.setInterval(() => void load(), 60_000)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [refreshToken])

  useEffect(() => {
    if (!container.current || map.current) return
    const instance = new MapLibreMap({ container: container.current, style: OMT_NEUTRAL_STYLE, center: [-47.95, -15.79], zoom: 10, attributionControl: { compact: true } })
    map.current = instance
    instance.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
    instance.on('load', () => {
      addSegmentLayers(instance)
      instance.on('click', 'segments-line', (event: MapLayerMouseEvent) => setSelectedId(String(event.features?.[0]?.properties?.id ?? '')))
      instance.on('mouseenter', 'segments-line', () => { instance.getCanvas().style.cursor = 'pointer' })
      instance.on('mouseleave', 'segments-line', () => { instance.getCanvas().style.cursor = '' })
      setReady(true)
    })
    const observer = new ResizeObserver(() => instance.resize()); observer.observe(container.current)
    return () => { observer.disconnect(); instance.remove(); map.current = null }
  }, [])

  useEffect(() => {
    if (!ready || !map.current || !data) return
    const geojson = collection(data.segments, showPlanned)
    ;(map.current.getSource('segments') as GeoJSONSource).setData(geojson)
    if (!fitted.current && geojson.features.length) {
      const coordinates = geojson.features.flatMap((feature) => feature.geometry.coordinates) as [number, number][]
      const bounds = coordinates.slice(1).reduce((value, point) => value.extend(point), new LngLatBounds(coordinates[0], coordinates[0]))
      map.current.fitBounds(bounds, { padding: 55, maxZoom: 14, duration: 600 }); fitted.current = true
    }
  }, [data, ready, showPlanned])

  useEffect(() => {
    if (!ready || !map.current) return
    const instance = map.current
    if (basemap === 'neutral' || basemap === 'dark') {
      if (styleFamily.current === basemap) return
      styleFamily.current = basemap
      const restore = () => { addSegmentLayers(instance); setReady((value) => !value); queueMicrotask(() => setReady(true)) }
      instance.once('style.load', restore)
      instance.setStyle(basemap === 'dark' ? OPENFREEMAP_DARK_STYLE : OMT_NEUTRAL_STYLE)
      return () => { instance.off('style.load', restore) }
    }
    if (styleFamily.current === 'satellite') return
    styleFamily.current = 'satellite'
    const restore = () => { addSegmentLayers(instance); instance.setLayoutProperty('osm', 'visibility', 'none'); instance.setLayoutProperty('satellite', 'visibility', 'visible'); setReady((value) => !value); queueMicrotask(() => setReady(true)) }
    instance.once('style.load', restore)
    instance.setStyle(STYLE)
    return () => { instance.off('style.load', restore) }
  }, [basemap, ready])

  useEffect(() => {
    if (!ready || !map.current) return
    const filter: FilterSpecification = ['==', ['get', 'id'], selectedId ?? '']
    map.current.setFilter('selected-segment-line', filter)
    map.current.setFilter('selected-segment-core', filter)
  }, [ready, selectedId])

  return <section className="segment-map-page">
    <div className="segment-map-toolbar">
      <div className="segment-map-summary"><strong>{data?.count ?? '—'} trechos</strong><span>Real {data?.source_counts.live ?? 0}</span><span>Histórica {data?.source_counts.historical ?? 0}</span><span>Planejada {data?.source_counts.gtfs_planned ?? 0}</span></div>
      <label className="toggle-control"><input type="checkbox" checked={showPlanned} onChange={(event) => setShowPlanned(event.target.checked)} /> Mostrar planejados</label>
      <div className="segment-speed-legend"><span className="red">≤ 10 km/h</span><span className="orange">10–20</span><span className="yellow">20–30</span><span className="green">&gt; 30</span><span className="planned">Planejada</span></div>
    </div>
    {error && <div className="inline-alert segment-map-error">{error}</div>}
    <div ref={container} className="map-canvas" aria-label="Mapa de velocidade real dos trechos" />
    <div className="basemap-switcher">{([['neutral', 'Neutro'], ['dark', 'Escuro'], ['satellite', 'Satélite']] as const).map(([value, label]) => <button key={value} className={basemap === value ? 'active' : ''} onClick={() => setBasemap(value)}>{label}</button>)}</div>
    {selected && <aside className="segment-detail-panel"><button onClick={() => setSelectedId(null)} aria-label="Fechar">×</button><span className="eyebrow">Trecho selecionado</span><h2>{selected.origin_stop_name}</h2><p>até {selected.destination_stop_name}</p><dl><div><dt>Velocidade</dt><dd>{selected.speed_kmh.toFixed(1)} km/h</dd></div><div><dt>Fonte</dt><dd>{selected.source === 'live' ? 'Real' : selected.source === 'historical' ? 'Histórica' : 'Planejada'}</dd></div><div><dt>Confiabilidade</dt><dd>{formatPercent(selected.reliability)}</dd></div><div><dt>Amostras</dt><dd>{selected.sample_count}</dd></div><div><dt>Tempo do trecho</dt><dd>{formatMinutes(selected.duration_seconds)}</dd></div><div><dt>Extensão</dt><dd>{formatDistance(selected.distance_m)}</dd></div></dl><small>Referência {formatClock(selected.window_end ?? data?.generated_at)}</small></aside>}
  </section>
}
