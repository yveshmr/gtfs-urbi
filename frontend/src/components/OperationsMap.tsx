import { useEffect, useRef, useState } from 'react'
import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import {
  GeoJSONSource,
  LngLatBounds,
  Map as MapLibreMap,
  type MapLayerMouseEvent,
  NavigationControl,
  setWorkerUrl,
  type SourceSpecification,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

import type { ProjectedVehiclePosition, TripGeometry } from '../types'
import { sliceLineBetweenFractions, splitLineAtFraction } from '../utils/geometry'

setWorkerUrl(workerUrl)

interface OperationsMapProps {
  vehicles: ProjectedVehiclePosition[]
  selectedVehicle: ProjectedVehiclePosition | null
  tripGeometry: TripGeometry | null
  onSelectVehicle: (vehiclePrefix: string) => void
}

const EMPTY_COLLECTION: FeatureCollection = { type: 'FeatureCollection', features: [] }
type Basemap = 'neutral' | 'dark' | 'satellite'

const OPENFREEMAP_DARK_STYLE = 'https://tiles.openfreemap.org/styles/dark'
const STANDARD_BASEMAP_LAYERS = {
  neutral: 'osm-neutral',
  satellite: 'satellite-imagery',
} as const
const OPERATIONAL_SOURCE_IDS = [
  'completed-route',
  'remaining-route',
  'current-segment',
  'trip-stops',
  'fleet-vehicles',
  'selected-vehicle',
] as const
const OPERATIONAL_LAYER_IDS = [
  'completed-route-line',
  'remaining-route-line',
  'current-segment-line',
  'trip-stop-points',
  'fleet-vehicle-points',
  'selected-vehicle-point',
] as const

const NEUTRAL_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    'osm-neutral-tiles': {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '&copy; OpenStreetMap contributors',
      maxzoom: 19,
    },
    'satellite-tiles': {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution: 'Tiles &copy; Esri and imagery providers',
      maxzoom: 19,
    },
    'completed-route': { type: 'geojson', data: EMPTY_COLLECTION },
    'remaining-route': { type: 'geojson', data: EMPTY_COLLECTION },
    'current-segment': { type: 'geojson', data: EMPTY_COLLECTION },
    'trip-stops': { type: 'geojson', data: EMPTY_COLLECTION },
    'fleet-vehicles': { type: 'geojson', data: EMPTY_COLLECTION },
    'selected-vehicle': { type: 'geojson', data: EMPTY_COLLECTION },
  },
  layers: [
    {
      id: 'neutral-background',
      type: 'background',
      paint: { 'background-color': '#ECF1F5' },
    },
    {
      id: 'osm-neutral',
      type: 'raster',
      source: 'osm-neutral-tiles',
    },
    {
      id: 'satellite-imagery',
      type: 'raster',
      source: 'satellite-tiles',
      layout: { visibility: 'none' },
    },
    {
      id: 'completed-route-line',
      type: 'line',
      source: 'completed-route',
      paint: { 'line-color': '#6B7280', 'line-width': 4, 'line-opacity': 0.72 },
    },
    {
      id: 'remaining-route-line',
      type: 'line',
      source: 'remaining-route',
      paint: { 'line-color': '#009CDF', 'line-width': 5, 'line-opacity': 0.95 },
    },
    {
      id: 'current-segment-line',
      type: 'line',
      source: 'current-segment',
      paint: { 'line-color': '#F2994A', 'line-width': 8, 'line-opacity': 0.94 },
    },
    {
      id: 'trip-stop-points',
      type: 'circle',
      source: 'trip-stops',
      paint: {
        'circle-radius': ['case', ['get', 'terminal'], 6, 3.5],
        'circle-color': ['case', ['get', 'terminal'], '#003B5C', '#FFFFFF'],
        'circle-stroke-color': '#005B7F',
        'circle-stroke-width': 2,
      },
    },
    {
      id: 'fleet-vehicle-points',
      type: 'circle',
      source: 'fleet-vehicles',
      paint: {
        'circle-radius': 7,
        'circle-color': [
          'case',
          ['==', ['get', 'quality'], 'valid'],
          '#009CDF',
          '#F2C94C',
        ],
        'circle-stroke-color': '#FFFFFF',
        'circle-stroke-width': 2,
        'circle-opacity': 0.94,
      },
    },
    {
      id: 'selected-vehicle-point',
      type: 'circle',
      source: 'selected-vehicle',
      paint: {
        'circle-radius': 11,
        'circle-color': '#003B5C',
        'circle-stroke-color': '#FFFFFF',
        'circle-stroke-width': 3,
      },
    },
  ],
}

function fleetCollection(vehicles: ProjectedVehiclePosition[]): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: vehicles.map((vehicle) => ({
      type: 'Feature',
      id: vehicle.vehicle_prefix,
      geometry: {
        type: 'Point',
        coordinates: [vehicle.longitude, vehicle.latitude],
      },
      properties: {
        vehiclePrefix: vehicle.vehicle_prefix,
        line: vehicle.route_short_name ?? vehicle.current_line ?? 'Sem linha',
        quality: vehicle.projection_quality,
      },
    })),
  }
}

function lineFeature(coordinates: [number, number][]): Feature<LineString> {
  return {
    type: 'Feature',
    properties: {},
    geometry: { type: 'LineString', coordinates },
  }
}

function updateSource(map: MapLibreMap, sourceId: string, data: FeatureCollection | Feature) {
  const source = map.getSource(sourceId)
  if (source && 'setData' in source) (source as GeoJSONSource).setData(data)
}

function addOperationalLayers(map: MapLibreMap) {
  for (const sourceId of OPERATIONAL_SOURCE_IDS) {
    if (!map.getSource(sourceId)) {
      const source = NEUTRAL_STYLE.sources[sourceId] as SourceSpecification
      map.addSource(sourceId, structuredClone(source))
    }
  }
  for (const layerId of OPERATIONAL_LAYER_IDS) {
    if (!map.getLayer(layerId)) {
      const layer = NEUTRAL_STYLE.layers.find((candidate) => candidate.id === layerId)
      if (layer) map.addLayer(structuredClone(layer))
    }
  }
}

function setStandardBasemap(map: MapLibreMap, basemap: 'neutral' | 'satellite') {
  for (const [name, layerId] of Object.entries(STANDARD_BASEMAP_LAYERS)) {
    map.setLayoutProperty(layerId, 'visibility', name === basemap ? 'visible' : 'none')
  }
}

export function OperationsMap({
  vehicles,
  selectedVehicle,
  tripGeometry,
  onSelectVehicle,
}: OperationsMapProps) {
  const container = useRef<HTMLDivElement | null>(null)
  const map = useRef<MapLibreMap | null>(null)
  const styleFamily = useRef<'standard' | 'dark'>('standard')
  const selectHandler = useRef(onSelectVehicle)
  const fittedTrip = useRef<string | null>(null)
  const [ready, setReady] = useState(false)
  const [styleRevision, setStyleRevision] = useState(0)
  const [basemap, setBasemap] = useState<Basemap>(() => {
    const saved = window.localStorage.getItem('gtfs-on-time-basemap')
    return saved === 'dark' || saved === 'satellite' ? saved : 'neutral'
  })

  selectHandler.current = onSelectVehicle

  useEffect(() => {
    if (!container.current || map.current) return
    const instance = new MapLibreMap({
      container: container.current,
      style: NEUTRAL_STYLE,
      center: [-47.95, -15.79],
      zoom: 10,
      attributionControl: { compact: true },
    })
    map.current = instance
    instance.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
    const initializeInteractions = () => {
      const selectVehicle = (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0]
        const prefix = feature?.properties?.vehiclePrefix as string | undefined
        if (prefix) selectHandler.current(prefix)
      }
      instance.on('click', 'fleet-vehicle-points', selectVehicle)
      instance.on('mouseenter', 'fleet-vehicle-points', () => {
        instance.getCanvas().style.cursor = 'pointer'
      })
      instance.on('mouseleave', 'fleet-vehicle-points', () => {
        instance.getCanvas().style.cursor = ''
      })
      setReady(true)
    }
    initializeInteractions()

    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(container.current)
    return () => {
      observer.disconnect()
      instance.remove()
      map.current = null
    }
  }, [])

  useEffect(() => {
    if (!ready || !map.current) return
    const instance = map.current
    window.localStorage.setItem('gtfs-on-time-basemap', basemap)

    if (basemap === 'dark') {
      if (styleFamily.current === 'dark') return
      styleFamily.current = 'dark'
      const restoreOperationalLayers = () => {
        addOperationalLayers(instance)
        setStyleRevision((revision) => revision + 1)
      }
      instance.once('style.load', restoreOperationalLayers)
      instance.setStyle(OPENFREEMAP_DARK_STYLE)
      return () => {
        instance.off('style.load', restoreOperationalLayers)
      }
    }

    if (styleFamily.current === 'dark') {
      styleFamily.current = 'standard'
      const restoreStandardStyle = () => {
        setStandardBasemap(instance, basemap)
        setStyleRevision((revision) => revision + 1)
      }
      instance.once('style.load', restoreStandardStyle)
      instance.setStyle(NEUTRAL_STYLE)
      return () => {
        instance.off('style.load', restoreStandardStyle)
      }
    }

    setStandardBasemap(instance, basemap)
  }, [basemap, ready])

  useEffect(() => {
    if (!ready || !map.current) return
    updateSource(map.current, 'fleet-vehicles', fleetCollection(vehicles))
  }, [ready, styleRevision, vehicles])

  useEffect(() => {
    if (!ready || !map.current) return
    const point: FeatureCollection<Point> = selectedVehicle
      ? {
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              geometry: {
                type: 'Point',
                coordinates: [selectedVehicle.longitude, selectedVehicle.latitude],
              },
              properties: {},
            },
          ],
        }
      : { type: 'FeatureCollection', features: [] }
    updateSource(map.current, 'selected-vehicle', point)
  }, [ready, selectedVehicle, styleRevision])

  useEffect(() => {
    if (!ready || !map.current || !tripGeometry || !selectedVehicle) {
      if (ready && map.current) {
        for (const id of ['completed-route', 'remaining-route', 'current-segment', 'trip-stops']) {
          updateSource(map.current, id, EMPTY_COLLECTION)
        }
      }
      return
    }

    const coordinates = tripGeometry.geometry.coordinates
    const route = splitLineAtFraction(coordinates, selectedVehicle.shape_position)
    updateSource(map.current, 'completed-route', lineFeature(route.completed))
    updateSource(map.current, 'remaining-route', lineFeature(route.remaining))

    const origin = tripGeometry.stops.find(
      (stop) => stop.stop_id === selectedVehicle.current_origin_stop_id,
    )
    const destination = tripGeometry.stops.find(
      (stop) => stop.stop_id === selectedVehicle.current_destination_stop_id,
    )
    const currentSegment =
      origin?.shape_position != null && destination?.shape_position != null
        ? lineFeature(
            sliceLineBetweenFractions(
              coordinates,
              origin.shape_position,
              destination.shape_position,
            ),
          )
        : EMPTY_COLLECTION
    updateSource(map.current, 'current-segment', currentSegment)

    const stopFeatures: FeatureCollection<Point> = {
      type: 'FeatureCollection',
      features: tripGeometry.stops
        .filter((stop) => stop.longitude != null && stop.latitude != null)
        .map((stop, index, stops) => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [stop.longitude!, stop.latitude!] },
          properties: {
            name: stop.stop_name,
            terminal: index === 0 || index === stops.length - 1,
          },
        })),
    }
    updateSource(map.current, 'trip-stops', stopFeatures)

    if (fittedTrip.current !== tripGeometry.trip_id && coordinates.length > 1) {
      const bounds = coordinates.reduce(
        (result, coordinate) => result.extend(coordinate),
        new LngLatBounds(coordinates[0], coordinates[0]),
      )
      map.current.fitBounds(bounds, {
        padding: { top: 120, right: 410, bottom: 80, left: 100 },
        duration: 700,
        maxZoom: 15,
      })
      fittedTrip.current = tripGeometry.trip_id
    }
  }, [ready, selectedVehicle, styleRevision, tripGeometry])

  return (
    <div className="map-shell">
      <div ref={container} className="map-canvas" aria-label="Mapa operacional da frota" />
      <div className="basemap-switcher" role="group" aria-label="Escolher mapa-base">
        {([
          ['neutral', 'Neutro'],
          ['dark', 'Escuro'],
          ['satellite', 'Satélite'],
        ] as const).map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={basemap === value ? 'active' : ''}
            aria-pressed={basemap === value}
            onClick={() => setBasemap(value)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
