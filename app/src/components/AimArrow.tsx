/**
 * The recommended aim on the map: a line from the ball along the aim direction for the
 * club's mean carry, with a 1 sigma dispersion ellipse at its end. Reads the store only.
 */
import type { GeoJSONSource, Map as MLMap } from 'maplibre-gl'
import type { FeatureCollection } from 'geojson'
import { useEffect, useMemo, useRef } from 'react'

import { gridToLonLat } from '../lib/geo'
import { lieAt } from '../lib/grid'
import { whenStyleReady } from '../lib/mapReady'
import { token } from '../lib/tokens'
import type { Lie, LieName, Meta, Player, XY } from '../lib/types'
import { useStore } from '../store'

export const ELLIPSE_POINTS = 32
/** The arrow is one of the three --rec elements (docs/design.md section 3). */
export function arrowColour(): string {
  return token('--color-rec')
}

/** Bearing from `p` to the pin in degrees: 0 along +y, positive to the golfer's right. */
export function pinBearingDeg(meta: Meta, p: XY): number {
  return (Math.atan2(meta.pin_xy[0] - p.x, meta.pin_xy[1] - p.y) * 180) / Math.PI
}

const LIE_NAMES: Partial<Record<Lie, LieName>> = { 1: 'tee', 2: 'fairway', 3: 'rough', 4: 'bunker', 5: 'fairway' }

export interface AimGeometry {
  line: [[number, number], [number, number]]
  ellipse: [number, number][]
  lateral_m: number
  along_m: number
}

/**
 * Grid-metre geometry of the aim for `club` and `dir_deg` from `ball` on lie `lie`.
 * Carry and sigmas use the player's lie multipliers as the solver does.
 */
export function aimGeometry(
  meta: Meta,
  player: Player,
  ball: XY,
  lie: Lie,
  rec: { club: string; dir_deg: number },
): AimGeometry {
  const club = player.clubs[rec.club]
  if (!club) throw new Error(`player has no club ${rec.club}`)
  const mult = player.lie[LIE_NAMES[lie] ?? 'fairway']
  const carry = club.mu_c * mult.carry
  const sigmaTheta = ((club.sigma_theta_deg * mult.sigma) * Math.PI) / 180
  const sigmaD = club.sigma_d * mult.sigma
  const a = ((pinBearingDeg(meta, ball) + rec.dir_deg) * Math.PI) / 180
  const ux = Math.sin(a)
  const uy = Math.cos(a)
  const end: [number, number] = [ball.x + carry * ux, ball.y + carry * uy]
  const lateral_m = carry * Math.tan(sigmaTheta)
  const along_m = carry * sigmaD
  const ellipse: [number, number][] = []
  for (let k = 0; k <= ELLIPSE_POINTS; k++) {
    const t = (2 * Math.PI * (k % ELLIPSE_POINTS)) / ELLIPSE_POINTS
    const lat = lateral_m * Math.cos(t) // across the aim
    const alo = along_m * Math.sin(t) // along the aim
    // across = (cos a, -sin a); along = (sin a, cos a)
    ellipse.push([end[0] + lat * Math.cos(a) + alo * ux, end[1] - lat * Math.sin(a) + alo * uy])
  }
  return { line: [[ball.x, ball.y], end], ellipse, lateral_m, along_m }
}

function toFeatures(meta: Meta, g: AimGeometry | null): FeatureCollection {
  if (!g) return { type: 'FeatureCollection', features: [] }
  const ll = ([x, y]: [number, number]): [number, number] => {
    const q = gridToLonLat(meta, { x, y })
    return [q.lon, q.lat]
  }
  return {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: { kind: 'line' }, geometry: { type: 'LineString', coordinates: g.line.map(ll) } },
      {
        type: 'Feature',
        properties: { kind: 'ellipse' },
        geometry: { type: 'Polygon', coordinates: [g.ellipse.map(ll)] },
      },
    ],
  }
}

export function AimArrow({ map }: { map: MLMap }) {
  const bundle = useStore((s) => s.bundle)
  const player = useStore((s) => s.player)
  const ball = useStore((s) => s.ball)
  const lieOverride = useStore((s) => s.lieOverride)
  const recommendation = useStore((s) => s.recommendation)

  // Geometry only changes with these inputs; drag frames that leave them alone cost nothing.
  const geometry = useMemo<AimGeometry | null>(() => {
    if (!bundle || !player || !ball || !recommendation) return null
    if (!(recommendation.club in player.clubs)) {
      // bundle and player.json disagree (e.g. the toy player with a real hole): no arrow
      console.warn(`aim arrow: player.json has no club ${recommendation.club}`)
      return null
    }
    const lie = lieOverride ?? lieAt(bundle, ball)
    return aimGeometry(bundle.meta, player, ball, lie, recommendation)
  }, [bundle, player, ball, lieOverride, recommendation])
  const lastRef = useRef<string>('')

  useEffect(() => {
    const apply = () => {
      const data = toFeatures(bundle?.meta ?? ({} as Meta), bundle ? geometry : null)
      const key = JSON.stringify(data)
      const source = map.getSource('aim') as GeoJSONSource | undefined
      if (source) {
        if (key !== lastRef.current) source.setData(data)
        lastRef.current = key
        return
      }
      lastRef.current = key
      const colour = arrowColour()
      map.addSource('aim', { type: 'geojson', data })
      map.addLayer({
        id: 'aim-ellipse',
        type: 'fill',
        source: 'aim',
        filter: ['==', ['get', 'kind'], 'ellipse'],
        paint: { 'fill-color': colour, 'fill-opacity': 0.22 },
      })
      map.addLayer({
        id: 'aim-ellipse-line',
        type: 'line',
        source: 'aim',
        filter: ['==', ['get', 'kind'], 'ellipse'],
        paint: { 'line-color': colour, 'line-width': 1.5 },
      })
      map.addLayer({
        id: 'aim-line',
        type: 'line',
        source: 'aim',
        filter: ['==', ['get', 'kind'], 'line'],
        paint: { 'line-color': colour, 'line-width': 3 },
      })
    }
    return whenStyleReady(map, apply)
  }, [map, bundle, geometry])

  return null
}
