import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { api } from './api'

/* ---------------- Theme ---------------- */
const ThemeCtx = createContext(null)

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'light')
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('ngui-theme', theme)
    } catch {
      /* storage unavailable */
    }
  }, [theme])

  // Circular reveal from the click point (View Transitions), plain swap otherwise.
  const toggle = useCallback(
    (e) => {
      const next = theme === 'dark' ? 'light' : 'dark'
      const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
      if (!document.startViewTransition || reduce) return setTheme(next)
      const x = e?.clientX ?? innerWidth / 2
      const y = e?.clientY ?? 0
      const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))
      const t = document.startViewTransition(() => {
        flushSync(() => setTheme(next))
        document.documentElement.dataset.theme = next
      })
      t.ready.then(() => {
        document.documentElement.animate(
          { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
          { duration: 650, easing: 'cubic-bezier(0.16, 1, 0.3, 1)', pseudoElement: '::view-transition-new(root)' },
        )
      })
    },
    [theme],
  )
  return <ThemeCtx.Provider value={{ theme, toggle }}>{children}</ThemeCtx.Provider>
}
export const useTheme = () => useContext(ThemeCtx)

/* ---------------- Backend health (polled) ---------------- */
const HealthCtx = createContext(null)

export function HealthProvider({ children }) {
  const [health, setHealth] = useState({ state: 'loading' })
  const check = useCallback(async () => {
    try {
      const h = await api.health()
      setHealth({ state: 'online', ...h })
    } catch (e) {
      setHealth({ state: 'offline', error: e })
    }
  }, [])
  useEffect(() => {
    check()
    const t = setInterval(check, 15000)
    return () => clearInterval(t)
  }, [check])
  return <HealthCtx.Provider value={{ ...health, recheck: check }}>{children}</HealthCtx.Provider>
}
export const useHealth = () => useContext(HealthCtx)

/* ---------------- useAsync: loading / error / data for one request ---------------- */
export function useAsync(fn, deps = []) {
  const [s, setS] = useState({ loading: true, error: null, data: null })
  const seq = useRef(0)
  const run = useCallback(async () => {
    const id = ++seq.current
    setS((p) => ({ ...p, loading: true, error: null }))
    try {
      const data = await fn()
      if (id === seq.current) setS({ loading: false, error: null, data })
    } catch (error) {
      if (id === seq.current) setS({ loading: false, error, data: null })
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    run()
  }, [run])
  return { ...s, reload: run, setData: (d) => setS((p) => ({ ...p, data: typeof d === 'function' ? d(p.data) : d })) }
}

/* ---------------- media query ---------------- */
export function useMedia(q) {
  const [m, setM] = useState(() => matchMedia(q).matches)
  useEffect(() => {
    const mq = matchMedia(q)
    const h = () => setM(mq.matches)
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [q])
  return m
}
