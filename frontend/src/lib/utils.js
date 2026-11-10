import clsx from 'clsx'

export const cn = (...a) => clsx(...a)

export const ms = (v) => {
  if (v == null || Number.isNaN(+v)) return '—'
  const n = +v
  if (n >= 10000) return `${(n / 1000).toFixed(1)} s`
  if (n >= 1000) return `${(n / 1000).toFixed(2)} s`
  return `${Math.round(n)} ms`
}
export const pct = (v, d = 0) => (v == null || Number.isNaN(+v) ? '—' : `${(+v * (Math.abs(+v) <= 1 ? 100 : 1)).toFixed(d)}%`)
export const num = (v, d = 2) => (v == null || Number.isNaN(+v) ? '—' : (+v).toLocaleString('en-IN', { maximumFractionDigits: d }))

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
export function ago(iso) {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const s = Math.round((t - Date.now()) / 1000)
  const a = Math.abs(s)
  if (a < 45) return 'just now'
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute')
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour')
  if (a < 86400 * 30) return rtf.format(Math.round(s / 86400), 'day')
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
export const fullDate = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '')

export const titleCase = (s = '') => String(s).replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export const reduceMotion = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

export const clone = (o) => (typeof structuredClone === 'function' ? structuredClone(o) : JSON.parse(JSON.stringify(o)))
