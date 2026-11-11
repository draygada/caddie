/**
 * Yardage pills drawn on the map the way course GPS apps do it: one at the pin with the
 * distance from the ball, one at the end of the aim arrow with the club and its carry.
 * They are HTML markers (the style has no glyph source for symbol layers). Reads the
 * store only.
 */
import { type Map as MLMap, Marker } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import { gridToLonLat } from '../lib/geo'
import { lieAt } from '../lib/grid'
import { clubDisplayName } from '../lib/tokens'
import type { Lie, LieName, Player, XY } from '../lib/types'
import { useStore } from '../store'
import { aimGeometry } from './AimArrow'
import { distanceToPinM, toYards } from './CaddiePanel'

const LIE_NAMES: Partial<Record<Lie, LieName>> = { 1: 'tee', 2: 'fairway', 3: 'rough', 4: 'bunker', 5: 'fairway' }

export function pinLabel(distanceM: number): string {
  return `${Math.round(toYards(distanceM))} yd`
}

/** "Driver · 241 yd": the club's mean carry from this lie. Null when the player lacks the club. */
export function aimLabel(player: Player, club: string, lie: Lie): string | null {
  const params = player.clubs[club]
  if (!params) return null
  const mult = player.lie[LIE_NAMES[lie] ?? 'fairway']
  return `${clubDisplayName(club)} · ${Math.round(toYards(params.mu_c * mult.carry))} yd`
}

const PILL = 'map-pill'

function makePill(): HTMLDivElement {
  const el = document.createElement('div')
  el.className = PILL
  el.setAttribute('aria-hidden', 'true')
  return el
}

/** Keep one marker at `at` with `text`, or remove it when either is null. */
function syncMarker(
  map: MLMap,
  ref: { current: Marker | null },
  lonLat: [number, number] | null,
  text: string | null,
  offset: [number, number],
): void {
  if (!lonLat || !text) {
    ref.current?.remove()
    ref.current = null
    return
  }
  if (!ref.current) {
    ref.current = new Marker({ element: makePill(), anchor: 'bottom', offset }).setLngLat(lonLat).addTo(map)
  } else {
    ref.current.setLngLat(lonLat)
  }
  ref.current.getElement().textContent = text
}

export function MapLabels({ map }: { map: MLMap }) {
  const bundle = useStore((s) => s.bundle)
  const player = useStore((s) => s.player)
  const ball = useStore((s) => s.ball)
  const lieOverride = useStore((s) => s.lieOverride)
  const recommendation = useStore((s) => s.recommendation)
  const pinRef = useRef<Marker | null>(null)
  const aimRef = useRef<Marker | null>(null)

  useEffect(() => {
    if (!bundle || !ball) {
      syncMarker(map, pinRef, null, null, [0, 0])
      syncMarker(map, aimRef, null, null, [0, 0])
      return
    }
    const meta = bundle.meta
    const pin: XY = { x: meta.pin_xy[0], y: meta.pin_xy[1] }
    const pinLL = gridToLonLat(meta, pin)
    syncMarker(map, pinRef, [pinLL.lon, pinLL.lat], pinLabel(distanceToPinM(meta, ball)), [0, -12])

    let aimLL: [number, number] | null = null
    let text: string | null = null
    if (player && recommendation && recommendation.club in player.clubs) {
      const lie = lieOverride ?? lieAt(bundle, ball)
      text = aimLabel(player, recommendation.club, lie)
      const g = aimGeometry(meta, player, ball, lie, recommendation)
      const end = gridToLonLat(meta, { x: g.line[1][0], y: g.line[1][1] })
      aimLL = [end.lon, end.lat]
    }
    syncMarker(map, aimRef, aimLL, text, [0, -10])
  }, [map, bundle, player, ball, lieOverride, recommendation])

  useEffect(
    () => () => {
      pinRef.current?.remove()
      aimRef.current?.remove()
      pinRef.current = null
      aimRef.current = null
    },
    [],
  )

  return null
}
