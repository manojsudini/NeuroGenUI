import { motion } from 'motion/react'
import { AlertTriangle, Check, Mic, Minus, Type, X } from 'lucide-react'
import { KIND_LABEL, STAGES } from '../../lib/ir'
import { cn, ms } from '../../lib/utils'
import { OpChip } from '../../components/common'
import { Badge } from '../../components/ui'
import { useStudio } from './Studio'

const EASE = [0.16, 1, 0.3, 1]

function Node({ status }) {
  return (
    <span
      className={cn(
        'relative z-10 grid size-6 shrink-0 place-items-center rounded-full border-2 bg-surface transition-colors duration-300',
        status === 'done' && 'border-accent bg-accent text-accent-fg',
        status === 'start' && 'ping-soft border-accent text-accent',
        status === 'error' && 'border-danger bg-danger text-white',
        status === 'skipped' && 'border-dashed border-line-strong text-subtle',
        status === 'idle' && 'border-line-strong text-subtle',
      )}
    >
      {status === 'done' && <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 600, damping: 22 }}><Check className="size-3.5" strokeWidth={3.2} /></motion.span>}
      {status === 'start' && <span className="size-2 rounded-full bg-accent" />}
      {status === 'error' && <X className="size-3.5" strokeWidth={3} />}
      {status === 'skipped' && <Minus className="size-3.5" />}
    </span>
  )
}

/** The run in progress, else the stored build of the version on screen, else an idle pipeline. */
function useTrace() {
  const { run, current } = useStudio()
  if (run) return { ...run, live: true }
  if (current?.timings) {
    const stages = Object.fromEntries(STAGES.map((s) => [s.id, current.timings[s.id] > 0 ? { status: 'done', ms: current.timings[s.id] } : { status: 'skipped', ms: null }]))
    return { live: false, active: false, stages, kind: current.kind, text: current.text, source: current.source, ops: current.ops || [], total: current.timings.total, score: current.validation?.score, version: current.number }
  }
  return { live: false, active: false, stages: Object.fromEntries(STAGES.map((s) => [s.id, { status: 'idle', ms: null }])), idle: true, ops: [] }
}

/**
 * Header of the Result card: step title, what ran, and the pipeline as a slim horizontal stepper.
 * Each stage lights up as its SSE "stage" event arrives, with the measured ms beneath it.
 */
export default function PipelineTrace() {
  const r = useTrace()
  const st = r.stages
  const doneIdx = STAGES.reduce((m, s, i) => (['done', 'skipped', 'error'].includes(st[s.id].status) ? i : m), -1)
  const activeIdx = STAGES.findIndex((s) => st[s.id].status === 'start')
  const reach = Math.max(doneIdx, activeIdx)
  const fill = reach < 0 ? 0 : reach / (STAGES.length - 1)
  const total = r.total ?? STAGES.reduce((a, s) => a + (st[s.id].ms || 0), 0)
  const hasOps = r.ops?.length > 0

  return (
    <div className="shrink-0 border-b border-line">
      <div className="flex h-14 items-center gap-3 px-4 pt-1">
        <h2 className="flex shrink-0 items-center gap-2.5 text-[15px] font-semibold tracking-tight">
          <span className="grid size-6 place-items-center rounded-full bg-accent-soft text-[12px] text-accent-soft-fg tnum">3</span>Result
        </h2>
        <div className="flex min-w-0 flex-1 items-center gap-2 text-[13px] text-muted">
          {r.idle ? (
            <span className="truncate">The build pipeline runs here once you generate.</span>
          ) : (
            <>
              <Badge tone={r.active ? 'accent' : 'neutral'} dot={r.active}>{r.active ? 'Running' : KIND_LABEL[r.kind] || r.kind || 'Build'}</Badge>
              {r.text && (
                <span className="flex min-w-0 items-center gap-1.5">
                  {r.source === 'voice' ? <Mic className="size-4 shrink-0 text-accent" /> : <Type className="size-4 shrink-0 text-subtle" />}
                  <span className="truncate">“{r.text}”</span>
                </span>
              )}
            </>
          )}
        </div>
        {!r.idle && (
          <div className="flex shrink-0 items-center gap-2">
            {!r.active && r.score != null && <Badge tone={r.score >= 0.85 ? 'success' : r.score >= 0.6 ? 'warning' : 'danger'} className="hidden font-mono sm:inline-flex">{Math.round(r.score * 100)}%</Badge>}
            <span className="font-mono text-[13px] text-muted tnum">{r.active ? 'running…' : ms(total)}</span>
          </div>
        )}
      </div>

      <div className="overflow-x-auto px-4 pt-1 pb-4 no-scrollbar">
        <div className="relative min-w-[560px]">
          <div className="absolute top-3 right-[calc(100%/18)] left-[calc(100%/18)] h-0.5 rounded-full bg-line" />
          <motion.div className="absolute top-3 left-[calc(100%/18)] h-0.5 rounded-full bg-accent" initial={false} animate={{ width: `calc((100% - 100%/9) * ${fill})` }} transition={{ duration: 0.6, ease: EASE }} />
          <ol className="relative grid grid-cols-9">
            {STAGES.map((s) => {
              const x = st[s.id]
              return (
                <li key={s.id} className="flex flex-col items-center gap-1.5 text-center">
                  <Node status={x.status} />
                  <span className={cn('text-[12px] leading-none whitespace-nowrap', x.status === 'start' ? 'font-medium text-accent' : x.status === 'idle' || x.status === 'skipped' ? 'text-subtle' : x.status === 'error' ? 'text-danger' : 'text-fg')}>{s.label}</span>
                  <span className="h-4 font-mono text-[12px] leading-4 text-muted tnum">
                    {x.status === 'start' ? <span className="text-accent">…</span> : x.ms != null && x.status !== 'skipped' ? ms(x.ms) : x.status === 'skipped' ? 'skip' : ''}
                  </span>
                </li>
              )
            })}
          </ol>
        </div>
      </div>

      {r.error && (
        <div className="mx-4 mb-4 flex items-start gap-2.5 rounded-xl bg-danger-soft px-3 py-2.5 text-[13px] text-danger">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /><span className="text-fg/85">{r.error}</span>
        </div>
      )}

      {hasOps && (
        <div className="flex items-start gap-3 border-t border-line bg-surface-2/50 px-4 py-2.5 [@media(max-height:820px)]:hidden">
          <span className="shrink-0 pt-1.5 text-[12px] text-subtle">Ops · {r.ops.length}</span>
          <div className="flex max-h-[40px] min-w-0 flex-1 flex-wrap gap-2 overflow-y-auto">
            {r.ops.map((o, i) => (
              <motion.div key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, duration: 0.3, ease: EASE }} className="max-w-full">
                <OpChip op={o} />
              </motion.div>
            ))}
          </div>
        </div>
      )}
      {r.changes?.some((c) => c.ok === false) && (
        <div className="space-y-0.5 border-t border-line px-4 py-2 text-[12px] text-warning">
          {r.changes.filter((c) => c.ok === false).map((c, i) => <div key={i}>• {c.op} {c.target}: {c.error || c.detail}</div>)}
        </div>
      )}
    </div>
  )
}
