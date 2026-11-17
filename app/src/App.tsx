import { useEffect, useState } from 'react'

import { HoleScreen } from './components/HoleScreen'
import { Home } from './components/Home'
import { loadBundle, loadPlayer } from './lib/loader'
import { prewarmTiles } from './lib/tiles'
import { useStore } from './store'

const THEME_KEY = 'caddie.theme'

function readTheme(): 'light' | 'dark' {
  try {
    return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export default function App() {
  const screen = useStore((s) => s.screen)
  const hole = useStore((s) => s.hole)
  const mode = useStore((s) => s.mode)
  const [error, setError] = useState<string | null>(null)
  const [theme, setTheme] = useState<'light' | 'dark'>(readTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      /* private mode: the toggle still works for this page */
    }
  }, [theme])

  useEffect(() => {
    loadPlayer()
      .then((player) => useStore.setState({ player }))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  useEffect(() => {
    let cancelled = false
    setError(null)
    loadBundle(hole, mode)
      .then((b) => {
        if (cancelled) return
        useStore.setState({ bundle: b, ball: null, lieOverride: null })
        // Part 14: cache the hole's satellite tiles while there is still a signal.
        if (b.meta.hole !== 'toy') void prewarmTiles(b.meta)
        const { tee: current, setTee: pick } = useStore.getState()
        pick(current in b.meta.tees ? current : 'black' in b.meta.tees ? 'black' : Object.keys(b.meta.tees)[0])
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [hole, mode])

  // Part 21: the home page first, every time. The bundle above keeps loading behind it.
  if (screen === 'home') return <Home />
  return (
    <HoleScreen
      screen={screen}
      theme={theme}
      onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
      error={error}
    />
  )
}
