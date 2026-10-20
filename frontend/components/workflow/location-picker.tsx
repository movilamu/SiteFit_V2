'use client'

import * as React from 'react'
import maplibregl, { type GeoJSONSource, type Map as MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

import { OPEN_TILE_STYLE_URL, OSM_RASTER_STYLE } from '@/lib/pilot-map'
import { cn } from '@/lib/utils'

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

const INDIA_CENTER: [number, number] = [80.27, 13.08]
const INDIA_ZOOM = 10

/**
 * Location picker.
 *
 * The map is a primary control here, not decoration: the user places the
 * search centre by clicking and sizes the search radius by dragging.  The
 * picked centre and radius are mirrored into the accessible controls below
 * the map so the same information is available without the map.
 */
export function LocationPicker({
  center,
  radiusKm,
  onChange,
  className,
}: {
  center: { latitude: number; longitude: number } | null
  radiusKm: number
  onChange: (next: { center: { latitude: number; longitude: number }; radiusKm: number }) => void
  className?: string
}) {
  const containerRef = React.useRef<HTMLDivElement | null>(null)
  const mapRef = React.useRef<MapLibreMap | null>(null)
  const markerRef = React.useRef<maplibregl.Marker | null>(null)
  const circleRef = React.useRef<maplibregl.Marker | null>(null)
  const readyRef = React.useRef(false)
  const onChangeRef = React.useRef(onChange)

  // The ref is updated in an effect rather than during render so that a
  // concurrent render cannot observe a half-updated value.
  React.useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  React.useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OPEN_TILE_STYLE_URL,
      center: center ? [center.longitude, center.latitude] : INDIA_CENTER,
      zoom: center ? 12 : INDIA_ZOOM,
    })
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'top-right')
    mapRef.current = map

    const onLoad = () => {
      map.addSource('search-radius', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'search-radius-fill',
        type: 'fill',
        source: 'search-radius',
        paint: { 'fill-color': '#1d4ed8', 'fill-opacity': 0.12 },
      })
      map.addLayer({
        id: 'search-radius-line',
        type: 'line',
        source: 'search-radius',
        paint: { 'line-color': '#1d4ed8', 'line-width': 1.5, 'line-opacity': 0.7 },
      })

      const centreMarker = document.createElement('button')
      centreMarker.type = 'button'
      centreMarker.className = 'location-picker-centre'
      centreMarker.setAttribute('aria-label', 'Search centre')
      markerRef.current = new maplibregl.Marker({ element: centreMarker, anchor: 'center' })
        .setLngLat(map.getCenter())
        .addTo(map)

      const radiusMarker = document.createElement('button')
      radiusMarker.type = 'button'
      radiusMarker.className = 'location-picker-radius'
      radiusMarker.setAttribute('aria-label', 'Search radius handle')
      circleRef.current = new maplibregl.Marker({ element: radiusMarker, anchor: 'center' })
        .setLngLat(map.getCenter())
        .addTo(map)

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

    return () => {
      markerRef.current?.remove()
      circleRef.current?.remove()
      markerRef.current = null
      circleRef.current = null
      map.remove()
      mapRef.current = null
      readyRef.current = false
    }
    // The map is created once; centre changes are handled by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Keep the overlays in sync with the controlled props.
  React.useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) return

    const apply = () => {
      const source = map.getSource('search-radius') as GeoJSONSource | undefined
      if (!source) return

      const origin = center ?? { latitude: INDIA_CENTER[1], longitude: INDIA_CENTER[0] }
      const edge = destinationPoint(
        origin.latitude,
        origin.longitude,
        radiusKm,
        90,
      )

      markerRef.current?.setLngLat([origin.longitude, origin.latitude])
      circleRef.current?.setLngLat([edge.longitude, edge.latitude])

      source.setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Polygon',
              coordinates: [
                Array.from({ length: 65 }, (_, index) => {
                  const bearing = index * 5.625
                  const point = destinationPoint(
                    origin.latitude,
                    origin.longitude,
                    radiusKm,
                    bearing,
                  )
                  return [point.longitude, point.latitude]
                }),
              ],
            },
          },
        ],
      })
    }

    if (map.isStyleLoaded()) {
      apply()
    } else {
      map.once('load', apply)
    }
  }, [center, radiusKm])

  // Click to move the centre.
  React.useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      const next = {
        latitude: Number(event.lngLat.lat.toFixed(6)),
        longitude: Number(event.lngLat.lng.toFixed(6)),
      }
      onChangeRef.current({ center: next, radiusKm })
    }

    map.on('click', handleClick)
    return () => {
      map.off('click', handleClick)
    }
  }, [radiusKm])

  return (
    <div className={cn('overflow-hidden rounded-lg border border-line', className)}>
      <div ref={containerRef} className="h-72 w-full sm:h-80" />
      <p className="text-ink-subtle border-line bg-surface-muted border-t px-3 py-2 text-[11px]">
        Click the map to set the search centre. Use the radius control below to size
        the search area.
      </p>
    </div>
  )
}

/**
 * Compute a destination point given a start point, distance and bearing.
 * Uses the spherical law of cosines, which is accurate enough for a
 * search-radius overlay.
 */
function destinationPoint(
  latitude: number,
  longitude: number,
  distanceKm: number,
  bearingDegrees: number,
): { latitude: number; longitude: number } {
  const radius = 6371.0088
  const angular = distanceKm / radius
  const bearing = (bearingDegrees * Math.PI) / 180
  const lat1 = (latitude * Math.PI) / 180
  const lon1 = (longitude * Math.PI) / 180

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular) +
      Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing),
  )
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
      Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
    )

  return {
    latitude: Number(((lat2 * 180) / Math.PI).toFixed(6)),
    longitude: Number(((lon2 * 180) / Math.PI).toFixed(6)),
  }
}
