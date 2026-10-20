'use client'

import { useEffect, useMemo, useRef } from 'react'
import maplibregl, { type GeoJSONSource, type Map as MapLibreMap, type Marker } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import './sites-map.css'

import {
  OPEN_TILE_STYLE_URL,
  OSM_RASTER_STYLE,
  PILOT_CENTER,
  PILOT_ZOOM,
  SITE_ZOOM,
  scoreBand,
} from '@/lib/pilot-map'

export type MapSite = {
  id: string
  name: string
  latitude: number
  longitude: number
  rank: number
  score: number | null
  excluded: boolean
}

type SitesMapProps = {
  sites: MapSite[]
  selectedSiteId: string | null
  onSelectSite: (id: string) => void
  catchment: GeoJSON.Geometry | null
  /** Centre the map on this point when it changes. */
  focus?: { latitude: number; longitude: number } | null
}

const EMPTY_COLLECTION: GeoJSON.FeatureCollection = {
  type: 'FeatureCollection',
  features: [],
}

function catchmentCollection(geometry: GeoJSON.Geometry | null): GeoJSON.FeatureCollection {
  if (!geometry) return EMPTY_COLLECTION
  return {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: {}, geometry }],
  }
}

function ensureCatchmentLayers(map: MapLibreMap) {
  if (!map.getSource('catchment')) {
    map.addSource('catchment', {
      type: 'geojson',
      data: EMPTY_COLLECTION,
    })
  }
  if (!map.getLayer('catchment-fill')) {
    map.addLayer({
      id: 'catchment-fill',
      type: 'fill',
      source: 'catchment',
      paint: {
        'fill-color': '#1d4ed8',
        'fill-opacity': 0.1,
      },
    })
  }
  if (!map.getLayer('catchment-outline')) {
    map.addLayer({
      id: 'catchment-outline',
      type: 'line',
      source: 'catchment',
      paint: {
        'line-color': '#1d4ed8',
        'line-width': 1.5,
        'line-opacity': 0.6,
      },
    })
  }
}

/**
 * The analytical map.
 *
 * The map is a working surface rather than a backdrop: sites carry their
 * rank, the selected site's catchment is drawn, and clicking a marker
 * selects that site.  The markers are DOM elements rather than map layers
 * so that they are keyboard reachable and announced to screen readers.
 */
export default function SitesMap({
  sites,
  selectedSiteId,
  onSelectSite,
  catchment,
  focus,
}: SitesMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markersRef = useRef<Map<string, Marker>>(new Map())
  const onSelectRef = useRef(onSelectSite)
  const selectedRef = useRef(selectedSiteId)
  const readyRef = useRef(false)
  const hasFittedRef = useRef(false)

  // Refs are updated in an effect rather than during render, so that a
  // concurrent render can never observe a half-updated value.
  useEffect(() => {
    onSelectRef.current = onSelectSite
  }, [onSelectSite])

  useEffect(() => {
    selectedRef.current = selectedSiteId
  }, [selectedSiteId])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    // The marker map is captured so the cleanup function works with the
    // exact instance it was created with.
    const markers = markersRef.current

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OPEN_TILE_STYLE_URL,
      center: PILOT_CENTER,
      zoom: PILOT_ZOOM,
    })
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'top-right')
    map.addControl(
      new maplibregl.GeolocateControl({ trackUserLocation: false }),
      'top-right',
    )
    mapRef.current = map

    const onLoad = () => {
      ensureCatchmentLayers(map)
      readyRef.current = true
      map.resize()
    }

    map.on('load', onLoad)
    map.on('error', (event: { error?: { message?: string } }) => {
      const message = event.error?.message || ''
      if (message.includes('style') || message.includes('fetch')) {
        map.setStyle(OSM_RASTER_STYLE)
      }
    })

    const resize = () => map.resize()
    window.addEventListener('resize', resize)

    return () => {
      window.removeEventListener('resize', resize)
      map.off('load', onLoad)
      markers.forEach((marker: maplibregl.Marker) => marker.remove())
      markers.clear()
      map.remove()
      mapRef.current = null
      readyRef.current = false
    }
  }, [])

  // Fit the viewport to the sites on first load.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current || hasFittedRef.current || sites.length === 0) return

    const bounds = new maplibregl.LngLatBounds()
    for (const site of sites) {
      bounds.extend([site.longitude, site.latitude])
    }
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 64, maxZoom: 13, duration: 0 })
      hasFittedRef.current = true
    }
  }, [sites])

  // Markers.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const existing = markersRef.current
    const nextIds = new Set(sites.map((site) => site.id))

    existing.forEach((marker: maplibregl.Marker, id: string) => {
      if (!nextIds.has(id)) {
        marker.remove()
        existing.delete(id)
      }
    })

    for (const site of sites) {
      let marker = existing.get(site.id)
      if (!marker) {
        const element = document.createElement('button')
        element.type = 'button'
        element.className = 'site-marker'
        element.addEventListener('click', (event) => {
          event.stopPropagation()
          onSelectRef.current(site.id)
        })
        marker = new maplibregl.Marker({ element, anchor: 'center' })
          .setLngLat([site.longitude, site.latitude])
          .addTo(map)
        existing.set(site.id, marker)
      } else {
        marker.setLngLat([site.longitude, site.latitude])
      }

      const element = marker.getElement()
      element.textContent = String(site.rank)
      element.dataset.band = scoreBand(site.score)
      element.setAttribute(
        'aria-label',
        `Rank ${site.rank}: ${site.name}${site.score !== null ? `, score ${site.score.toFixed(3)}` : ''}`,
      )
      element.classList.toggle('is-selected', selectedRef.current === site.id)
      element.classList.toggle('is-excluded', site.excluded)
    }
  }, [sites])

  // Selection highlight and focus.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    markersRef.current.forEach((marker: maplibregl.Marker, id: string) => {
      marker.getElement().classList.toggle('is-selected', id === selectedSiteId)
    })

    if (focus) {
      const fly = () => {
        map.flyTo({
          center: [focus.longitude, focus.latitude],
          zoom: Math.max(map.getZoom(), SITE_ZOOM),
          essential: true,
          duration: 800,
        })
      }
      if (readyRef.current) fly()
      else map.once('load', fly)
    }
  }, [selectedSiteId, sites, focus])

  // Catchment overlay.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const apply = () => {
      ensureCatchmentLayers(map)
      const source = map.getSource('catchment') as GeoJSONSource | undefined
      source?.setData(catchmentCollection(catchment))
    }

    if (readyRef.current && map.isStyleLoaded()) {
      apply()
    } else {
      map.once('load', apply)
    }
  }, [catchment])

  const selected = useMemo(
    () => sites.find((site) => site.id === selectedSiteId) ?? null,
    [sites, selectedSiteId],
  )

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="sites-map absolute inset-0" />
      {selected ? (
        <div className="border-line bg-surface/95 pointer-events-none absolute top-3 left-3 max-w-[280px] rounded-md border px-3 py-2 shadow-sm backdrop-blur">
          <p className="text-ink truncate text-[13px] font-semibold">{selected.name}</p>
          <p className="text-ink-muted text-[11px]">
            Rank {selected.rank}
            {selected.score !== null ? ` · score ${selected.score.toFixed(3)}` : ''}
          </p>
        </div>
      ) : null}
    </div>
  )
}
