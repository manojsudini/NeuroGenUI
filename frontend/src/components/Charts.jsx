import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// Series colours, all themed via CSS vars: accent first, then quiet neutrals and status hues.
export const SERIES = ['var(--accent)', 'var(--fg)', 'var(--info)', 'var(--warning)', 'var(--success)', 'var(--fg-subtle)', 'var(--danger)']
const axis = { stroke: 'var(--fg-subtle)', fontSize: 11.5, tickLine: false, axisLine: false }
const tick = (v) => (typeof v !== 'number' ? v : Math.abs(v) >= 1000 ? new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(v) : Math.abs(v) < 1 && v !== 0 ? +v.toFixed(2) : +v.toFixed(1))
const fmt = (v) => (typeof v === 'number' ? (Math.abs(v) < 1 && v !== 0 ? v.toFixed(3) : v.toLocaleString('en-IN', { maximumFractionDigits: 2 })) : v)

function Tip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null
  return (
    <div className="min-w-36 rounded-xl border border-line bg-surface px-3 py-2.5 text-[13px] shadow-pop">
      <div className="mb-1.5 font-medium text-muted">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted"><span className="size-2 rounded-full" style={{ background: p.color }} />{p.name}</span>
          <span className="font-mono font-medium tnum">{fmt(p.value)}{unit ? ` ${unit}` : ''}</span>
        </div>
      ))}
    </div>
  )
}
function LegendRow({ payload }) {
  return (
    <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[12px] text-muted">
      {payload.map((p) => <span key={p.value} className="flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: p.color }} />{p.value}</span>)}
    </div>
  )
}

/** Generic chart from the evaluation summary: {type: bar|line|stacked, x, series:[key|{key,name}], data:[...]} */
// Accepts both shapes: a list of row objects (x names the key), or {series: {category: value}} with x = [categories].
export function chartRows(chart) {
  const d = chart.data
  if (Array.isArray(d)) return { rows: d, xKey: chart.x }
  if (d && typeof d === 'object' && Array.isArray(chart.x)) {
    const rows = chart.x.map((cat) => {
      const row = { __x: cat }
      for (const k of Object.keys(d)) row[k] = d[k]?.[cat] ?? null
      return row
    })
    return { rows, xKey: '__x' }
  }
  return { rows: [], xKey: chart.x }
}

export function GenericChart({ chart, height = 260 }) {
  const series = (chart.series || []).map((s, i) => (typeof s === 'string' ? { key: s, name: s, color: SERIES[i % SERIES.length] } : { key: s.key, name: s.name || s.key, color: SERIES[i % SERIES.length] }))
  const { rows: data, xKey } = chartRows(chart)
  const common = { data, margin: { top: 8, right: 12, left: 0, bottom: 0 } }
  const yAxis = <YAxis {...axis} width={48} tickFormatter={tick} />
  const many = data.length > 6
  const xAxis = <XAxis dataKey={xKey} {...axis} dy={many ? 4 : 6} interval={0} tick={{ fontSize: 11 }} angle={many ? -28 : 0} textAnchor={many ? 'end' : 'middle'} height={many ? 58 : 30} />
  const grid = <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 4" />
  const legend = series.length > 1 ? <Legend content={<LegendRow />} /> : null
  return (
    <ResponsiveContainer width="100%" height={height}>
      {chart.type === 'line' ? (
        <LineChart {...common}>
          {grid}{xAxis}{yAxis}
          <Tooltip content={<Tip unit={chart.unit} />} cursor={{ stroke: 'var(--border-strong)', strokeDasharray: '3 3' }} />
          {legend}
          {series.map((s) => <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} dot={{ r: 3, strokeWidth: 0, fill: s.color }} activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--surface)' }} animationDuration={900} />)}
        </LineChart>
      ) : (
        <BarChart {...common} barGap={3}>
          {grid}{xAxis}{yAxis}
          <Tooltip content={<Tip unit={chart.unit} />} cursor={{ fill: 'var(--surface-hover)', radius: 8 }} />
          {legend}
          {series.map((s, i) => <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} stackId={chart.type === 'stacked' ? 'a' : undefined} radius={chart.type === 'stacked' ? (i === series.length - 1 ? [5, 5, 0, 0] : [0, 0, 0, 0]) : [5, 5, 1, 1]} maxBarSize={34} animationDuration={800} />)}
        </BarChart>
      )}
    </ResponsiveContainer>
  )
}
