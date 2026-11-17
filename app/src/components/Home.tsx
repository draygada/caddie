/**
 * The home page (part 21): the first screen, every time. Two cards, one per posture in
 * docs/design.md section 1. Tapping "Play with GPS" is also the user gesture iOS Safari
 * needs before it hands out a position.
 */
import { type Screen, useStore } from '../store'

export const HOME_TAGLINE = 'The club and the aim with the fewest expected strokes, on holes 10 to 12 at Stanford.'

export const MODES_ON_HOME: { screen: Exclude<Screen, 'home'>; where: string; title: string; body: string }[] = [
  {
    screen: 'simulate',
    where: 'At a desk',
    title: 'Simulate a hole',
    body: 'Put the ball anywhere on a hole. See the best club and aim from there, then play the hole out.',
  },
  {
    screen: 'play',
    where: 'On the course',
    title: 'Play with GPS',
    body: 'Follows you as you walk and logs each shot you hit. Asks for your location.',
  },
]

export function Home() {
  const setScreen = useStore((s) => s.setScreen)
  return (
    <main className="safe-top safe-bottom flex h-full flex-col bg-surface px-5 text-ink">
      <div className="mx-auto flex h-full w-full max-w-md flex-col">
        <header className="flex flex-1 flex-col justify-center gap-3 py-8">
          <h1 className="leading-none" style={{ fontSize: 'var(--text-hero)', fontWeight: 700 }}>
            Caddie
          </h1>
          <p className="max-w-[30ch] text-body text-ink-2">{HOME_TAGLINE}</p>
        </header>
        <nav className="flex flex-col gap-3 pb-8" aria-label="Choose a mode">
          {MODES_ON_HOME.map((m) => (
            <button
              key={m.screen}
              type="button"
              className="group flex min-h-[112px] items-center gap-4 rounded-2xl border border-line bg-surface-2 p-5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.06)] transition-colors hover:border-ink active:bg-surface"
              onClick={() => setScreen(m.screen)}
            >
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="label">{m.where}</span>
                <span className="text-ink" style={{ fontSize: '22px', fontWeight: 600, lineHeight: 1.2 }}>
                  {m.title}
                </span>
                <span className="text-body text-ink-2">{m.body}</span>
              </span>
              <svg
                viewBox="0 0 24 24"
                width="24"
                height="24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="shrink-0 text-ink-2 transition-transform group-hover:translate-x-0.5 group-hover:text-rec"
                aria-hidden="true"
              >
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          ))}
        </nav>
      </div>
    </main>
  )
}
