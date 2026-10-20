import type { StyleSpecification } from 'maplibre-gl'

/** Greater Chennai / GCC pilot area (File 12/13 bbox: 12.85–13.25 N, 80.10–80.35 E). */
export const PILOT_CENTER: [number, number] = [80.225, 13.05]
export const PILOT_ZOOM = 11
export const SITE_ZOOM = 14

/**
 * OpenStreetMap-based vector tiles via OpenFreeMap.  No API key is
 * required and the "positron" style is a light, low-saturation basemap
 * that keeps the analytical overlays legible.
 */
export const OPEN_TILE_STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'

/** OSM-based raster fallback (Carto Positron, OSM data). */
export const OSM_RASTER_STYLE: StyleSpecification = {
  version: 8,
  name: 'OSM raster',
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors © CARTO',
      maxzoom: 19,
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}

/**
 * Score bands used to colour the map markers.
 *
 * The band is expressed in words and in colour, and the marker carries the
 * site's rank number so the meaning never depends on colour alone.
 */
export const SCORE_BANDS = [
  { key: 'strong', label: 'Strong', min: 0.66, token: 'success' },
  { key: 'moderate', label: 'Moderate', min: 0.4, token: 'info' },
  { key: 'weak', label: 'Weak', min: 0.2, token: 'warning' },
  { key: 'poor', label: 'Poor', min: 0, token: 'danger' },
] as const

export type ScoreBandKey = (typeof SCORE_BANDS)[number]['key']

export function scoreBand(score: number | null | undefined): ScoreBandKey {
  if (score === null || score === undefined || !Number.isFinite(score)) return 'poor'
  for (const band of SCORE_BANDS) {
    if (score >= band.min) return band.key
  }
  return 'poor'
}
