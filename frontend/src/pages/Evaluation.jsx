import { motion } from 'motion/react'
import { ArrowDownRight, ArrowUpRight, Clock, FlaskConical, ImageIcon, Info as InfoIcon, Table2 } from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/store'
import { cn, fullDate, titleCase } from '../lib/utils'
import { GenericChart, chartRows } from '../components/Charts'
import { Badge, Card, CardHeader, CountUp, Empty, ErrorState, PageHeader, Skeleton, stagger } from '../components/ui'

// Which direction is better is decided per metric (never guessed from the unit).
const LOWER_BETTER = new Set(['whisper_wer', 'generation_time_ms', 'modification_time_ms', 'code_eslint_messages', 'code_max_function_lines'])
const LABELS = {
  component_detection_f1: 'Detection F1 (analysis)',
  component_detection_f1_dom: 'Detection F1 (rendered UI)',
  whisper_wer: 'Whisper word error rate',
  voice_command_accuracy: 'Voice command accuracy',
  visual_similarity_layout_iou: 'Layout IoU vs sketch',
  visual_similarity_edge_ssim: 'Edge SSIM vs sketch',
  functional_correctness: 'Functional correctness',
  requirement_satisfaction: 'Requirement satisfaction',
  refinement_success_rate: 'Refinement success rate',
  preservation_rate: 'Unaffected components preserved',
  validation_pass_rate_before_repair: 'Validation pass, before repair',
  validation_pass_rate_after_repair: 'Validation pass, after repair',
  fault_detection_rate: 'Injected faults detected',
  fault_repair_rate: 'Injected faults repaired',
  generation_time_ms: 'Generation time (mean)',
  modification_time_ms: 'Voice refinement time (mean)',
  code_parse_rate: 'Generated code parses',
  code_eslint_messages: 'ESLint messages per UI',
  code_reuse_ratio: 'Component reuse ratio',
  code_max_function_lines: 'Longest function (lines)',
}

function fmtMetric(v, unit) {
  if (v == null || Number.isNaN(+v)) return '—'
  const n = +v
  if (unit === '%') return `${(Math.abs(n) <= 1 ? n * 100 : n).toFixed(1)}%`
  if (unit === 'ms') return n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${Math.round(n)} ms`
  if (unit === 's') return `${n.toFixed(2)} s`
  return `${n.toLocaleString('en-IN', { maximumFractionDigits: Math.abs(n) < 10 ? 3 : 1 })}${unit && unit !== 'ratio' && unit !== 'score' ? ` ${unit}` : ''}`
}
function countFormat(unit, sample) {
  return (x) => {
    if (unit === '%') return `${(Math.abs(sample) <= 1 ? x * 100 : x).toFixed(1)}%`
    return fmtMetric(x, unit)
  }
}

const GROUPS = [
  { title: 'Detection', keys: ['component_detection_f1', 'component_detection_f1_dom'] },
  { title: 'Voice', keys: ['whisper_wer', 'voice_command_accuracy'] },
  { title: 'Generated UI quality', keys: ['visual_similarity_layout_iou', 'visual_similarity_edge_ssim', 'functional_correctness', 'requirement_satisfaction'] },
  { title: 'Refinement', keys: ['refinement_success_rate', 'preservation_rate'] },
  { title: 'Speed', keys: ['generation_time_ms', 'modification_time_ms'] },
  { title: 'Validation & repair', keys: ['validation_pass_rate_before_repair', 'validation_pass_rate_after_repair', 'fault_detection_rate', 'fault_repair_rate'] },
  { title: 'Code quality', keys: ['code_parse_rate', 'code_eslint_messages', 'code_reuse_ratio', 'code_max_function_lines'] },
]
const SPAN = { 1: 'lg:col-span-1', 2: 'lg:col-span-2', 3: 'lg:col-span-3', 4: 'lg:col-span-4' }
const INNER = { 1: 'lg:grid-cols-1', 2: 'lg:grid-cols-2', 3: 'lg:grid-cols-3', 4: 'lg:grid-cols-4' }

function verdict(name, m) {
  const p = m?.pipeline
  const b = m?.baseline
  const lower = LOWER_BETTER.has(name)
  const hasB = b != null && !Number.isNaN(+b) && +b !== 0
  const rel = hasB ? ((+p - +b) / Math.abs(+b)) * 100 : null
  const equal = rel != null && Math.abs(rel) < 0.05
  const better = rel == null || equal ? null : lower ? rel < 0 : rel > 0
  return { lower, hasB, rel, equal, better }
}

function Info({ text }) {
  return (
    <span className="group/tip relative shrink-0">
      <button type="button" aria-label="What this measures" className="grid size-6 place-items-center rounded-md text-subtle transition-colors hover:bg-surface-hover hover:text-fg focus-visible:bg-surface-hover"><InfoIcon className="size-4" strokeWidth={1.8} /></button>
      <span role="tooltip" className="pointer-events-none absolute top-full right-0 z-20 mt-2 w-64 rounded-xl border border-line bg-surface p-3 text-[13px] leading-snug font-normal text-muted opacity-0 shadow-pop transition-opacity duration-150 group-focus-within/tip:opacity-100 group-hover/tip:opacity-100">{text}</span>
    </span>
  )
}

function MetricTile({ name, m, i }) {
  const p = m?.pipeline
  const b = m?.baseline
  const { lower, rel, equal, better } = verdict(name, m)
  const tip = [m?.description, lower && 'Lower is better.'].filter(Boolean).join(' ')
  return (
    <motion.div {...stagger(i, 0.04)} className="h-full">
      <Card className="flex h-full min-h-[148px] flex-col p-5 transition-shadow hover:shadow-card">
        <div className="flex min-h-6 items-start justify-between gap-2">
          <span className="text-[13px] leading-6 text-muted">{LABELS[name] || titleCase(name)}</span>
          {tip && <Info text={tip} />}
        </div>
        <div className="mt-3 text-[28px] leading-none font-semibold tracking-[-0.03em] tnum">
          {typeof p === 'number' ? <CountUp value={p} format={countFormat(m.unit, p)} /> : fmtMetric(p, m?.unit)}
        </div>
        <div className="mt-auto flex items-center justify-between gap-2 pt-4 text-[12px]">
          <span className="text-subtle">{b != null ? <>Baseline <span className="font-mono text-muted tnum">{fmtMetric(b, m.unit)}</span></> : 'No baseline'}</span>
          {equal && <span className="text-subtle">Same</span>}
          {rel != null && !equal && Number.isFinite(rel) && (
            <span className={`inline-flex items-center gap-0.5 tnum ${better ? 'text-success' : 'text-danger'}`}>
              {rel >= 0 ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}{Math.abs(rel).toFixed(1)}%
            </span>
          )}
        </div>
      </Card>
    </motion.div>
  )
}

function MetricGroups({ metrics }) {
  const byKey = Object.fromEntries(metrics)
  const used = new Set()
  const groups = GROUPS.map((g) => ({ title: g.title, items: g.keys.filter((k) => byKey[k]).map((k) => (used.add(k), [k, byKey[k]])) })).filter((g) => g.items.length)
  const rest = metrics.filter(([k]) => !used.has(k))
  if (rest.length) groups.push({ title: 'Other', items: rest })
  let n = 0
  return (
    <div className="grid gap-x-4 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
      {groups.map((g) => {
        const cols = Math.min(g.items.length, 4)
        return (
          <section key={g.title} className={cn('col-span-1 sm:col-span-2', SPAN[cols])}>
            <h2 className="mb-4 flex items-baseline gap-2 text-[15px] font-semibold tracking-tight">{g.title}<span className="text-[13px] font-normal text-subtle">{g.items.length}</span></h2>
            <div className={cn('grid gap-4 sm:grid-cols-2', INNER[cols])}>
              {g.items.map(([k, m]) => <MetricTile key={k} name={k} m={m} i={n++} />)}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function Cell({ v }) {
  if (v == null) return <span className="text-subtle">—</span>
  if (typeof v === 'number') return <span className="font-mono tnum">{Number.isInteger(v) ? v.toLocaleString('en-IN') : v.toFixed(Math.abs(v) < 1 ? 3 : 2)}</span>
  if (typeof v === 'boolean') return <Badge tone={v ? 'success' : 'danger'}>{v ? 'pass' : 'fail'}</Badge>
  return <span>{String(v)}</span>
}

export default function Evaluation() {
  const r = useAsync(() => api.evaluation(), [])
  const missing = r.error?.status === 404

  if (r.loading) {
    return (
      <div>
        <Skeleton className="mb-2 h-4 w-28" /><Skeleton className="mb-6 h-7 w-56" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}</div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-80 rounded-2xl" />)}</div>
      </div>
    )
  }
  if (r.error && !missing) return <><PageHeader eyebrow="Research results" title="Evaluation" /><Card><ErrorState error={r.error} onRetry={r.reload} /></Card></>
  if (missing || !r.data) {
    return (
      <div>
        <PageHeader eyebrow="Research results" title="Evaluation" desc="Pipeline vs the direct sketch → AI → UI baseline, measured on the same dataset." />
        <Card className="overflow-hidden">
          <Empty image="/img/markers-sketch.jpg" title="No evaluation results yet" desc="Run the evaluation scripts in project/evaluation. When evaluation/results/latest/summary.json exists, the metrics, charts and tables appear here." />
        </Card>
      </div>
    )
  }

  const d = r.data
  const metrics = Object.entries(d.metrics || {})
  const charts = d.charts || []
  const tables = d.tables || []
  const plots = d.plots || d.plot_urls || []
  const beat = metrics.reduce((a, [k, m]) => { const v = verdict(k, m); return v.better == null ? a : { better: a.better + (v.better ? 1 : 0), total: a.total + 1 } }, { better: 0, total: 0 })
  const nothing = !metrics.length && !charts.length && !tables.length && !plots.length

  return (
    <div>
      <PageHeader
        eyebrow="Research results"
        title="Evaluation"
        desc="The pipeline against a direct sketch → AI → UI baseline, measured on the same dataset."
        actions={<>{beat.total > 0 && <Badge tone="success"><ArrowUpRight className="size-3.5" />{beat.better} of {beat.total} beat the baseline</Badge>}{d.generated_at && <Badge><Clock className="size-3.5" />Generated {fullDate(d.generated_at)}</Badge>}</>}
      />
      {nothing && <Card><Empty icon={FlaskConical} title="The summary is empty" desc="summary.json exists but has no metrics, charts, tables or plots yet." /></Card>}

      {metrics.length > 0 && <MetricGroups metrics={metrics} />}

      {charts.length > 0 && <h2 className="mt-14 mb-4 flex items-baseline gap-2 text-[15px] font-semibold tracking-tight">Charts<span className="text-[13px] font-normal text-subtle">{charts.length}</span></h2>}
      {charts.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {charts.map((c, i) => (
            <motion.div key={c.title + i} {...stagger(i, 0.06)} className={charts.length % 2 === 1 && i === charts.length - 1 ? 'lg:col-span-2' : ''}>
              <Card className="h-full">
                <CardHeader title={c.title} desc={c.description} action={<Badge>{titleCase(c.type || 'bar')}</Badge>} />
                <div className="px-3 pb-4">{chartRows(c).rows.length ? <GenericChart chart={c} /> : <p className="px-2 py-10 text-center text-[13px] text-subtle">No data points.</p>}</div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      {tables.map((t, i) => (
        <Card key={t.title + i} className="mt-6 overflow-hidden">
          <CardHeader icon={Table2} title={t.title} desc={t.description} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-[13px]">
              <thead className="border-y border-line bg-surface-2/60 text-[12px] text-subtle">
                <tr>{(t.columns || []).map((c, j) => <th key={j} className="px-4 py-2.5 font-medium">{c}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {(t.rows || []).map((row, j) => (
                  <tr key={j} className="hover:bg-surface-hover/50">{(Array.isArray(row) ? row : (t.columns || []).map((c) => row[c])).map((v, k) => <td key={k} className="px-4 py-2.5"><Cell v={v} /></td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}

      {plots.length > 0 && (
        <section className="mt-14">
          <h2 className="mb-3 flex items-center gap-2 text-[16px] font-semibold tracking-tight"><ImageIcon className="size-4 text-subtle" />Plots for the paper</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {plots.map((u) => (
              <a key={u} href={u} target="_blank" rel="noreferrer" className="group overflow-hidden rounded-2xl border border-line bg-white transition-shadow hover:shadow-card">
                <img src={u} alt={u.split('/').pop()} loading="lazy" className="w-full transition-transform duration-700 ease-out-expo group-hover:scale-[1.02]" />
                <div className="border-t border-line bg-surface px-3 py-2 font-mono text-[12px] text-muted">{u.split('/').pop()}</div>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
