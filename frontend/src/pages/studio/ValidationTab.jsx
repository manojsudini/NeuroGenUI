import { useState } from 'react'
import { motion } from 'motion/react'
import { AlertOctagon, Check, Eye, MousePointerClick, ShieldCheck, Wrench, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, errMessage } from '../../lib/api'
import { cn, ms, pct } from '../../lib/utils'
import { Badge, Button, Empty, Progress, ScoreRing, Segmented } from '../../components/ui'
import { NotGenerated, useStudio } from './Studio'

function Check1({ c, i }) {
  return (
    <motion.li initial={{ opacity: 0, x: 6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 20) * 0.02 }} className="flex items-start gap-3 px-3 py-2.5">
      <span className={cn('mt-0.5 grid size-5 shrink-0 place-items-center rounded-full', c.ok ? 'bg-success-soft text-success' : 'bg-danger-soft text-danger')}>{c.ok ? <Check className="size-3" strokeWidth={3} /> : <X className="size-3" strokeWidth={3} />}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium">{c.name}{c.target && <span className="font-mono text-[12px] font-normal text-subtle">{c.target}</span>}</div>
        {c.detail && <div className="mt-0.5 text-[12px] break-words text-muted">{c.detail}</div>}
      </div>
    </motion.li>
  )
}

export default function ValidationTab() {
  const s = useStudio()
  const v = s.current
  const [busy, setBusy] = useState(null)
  const [report, setReport] = useState(null) // fresh report from "Validate"
  const [filter, setFilter] = useState('all')
  if (!v) return <NotGenerated what="The validation report" />

  const rep = report?.forVersion === v.number ? report.data : v.validation
  const repairs = (report?.forVersion === v.number && report.data.repairs) || v.repairs || []

  const go = async (repair) => {
    setBusy(repair ? 'repair' : 'validate')
    try {
      const r = await api.validate(s.id, v.number, repair)
      if (r.new_version) {
        const nv = typeof r.new_version === 'object' ? r.new_version : await api.version(s.id, r.new_version)
        s.adopt(nv, 'Repaired')
      } else {
        setReport({ forVersion: v.number, data: r })
        toast.success(r.passed ? 'All checks passed' : 'Validation finished', { description: `Score ${Math.round((r.score ?? 0) * 100)}%${repair ? ' · nothing needed repair' : ''}` })
      }
    } catch (e) {
      toast.error('Validation failed to run', { description: errMessage(e) })
    } finally {
      setBusy(null)
    }
  }

  const checks = rep?.checks || []
  const shown = checks.filter((c) => filter === 'all' || (filter === 'failed' ? !c.ok : c.kind === filter))
  const vis = checks.filter((c) => c.kind === 'visual')
  const fun = checks.filter((c) => c.kind === 'functional')
  const errs = rep?.functional?.runtime_errors || []
  const shot = rep?.screenshot_url || (rep?.screenshot_b64 ? `data:image/png;base64,${rep.screenshot_b64}` : null)

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-4">
        <Button size="xs" variant="secondary" icon={ShieldCheck} loading={busy === 'validate'} disabled={!!busy} onClick={() => go(false)}>Validate</Button>
        <Button size="xs" icon={Wrench} loading={busy === 'repair'} disabled={!!busy} onClick={() => go(true)}>Validate + repair</Button>
        {rep?.duration_ms != null && <span className="ml-auto font-mono text-[12px] text-subtle">{ms(rep.duration_ms)}</span>}
      </div>
      {!rep ? (
        <Empty compact icon={ShieldCheck} title="Not validated yet" desc="Run the validator: Playwright renders this version and checks presence, layout and every interaction." />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="flex items-center gap-5 p-4">
            <ScoreRing value={rep.score} label="score" />
            <div className="min-w-0 flex-1 space-y-3">
              <Badge tone={rep.passed ? 'success' : 'danger'} dot>{rep.passed ? 'Passed' : 'Needs attention'}</Badge>
              {rep.visual && (
                <div className="space-y-1.5">
                  {[['Presence', rep.visual.presence], ['Layout IoU', rep.visual.layout_iou], ['Order', rep.visual.order_consistency]].filter(([, x]) => x != null).map(([k, x]) => (
                    <div key={k} className="grid grid-cols-[80px_1fr_40px] items-center gap-2 text-[12px]"><span className="text-muted">{k}</span><Progress value={x * 100} tone={x >= 0.85 ? 'success' : x >= 0.6 ? 'warning' : 'danger'} /><span className="text-right font-mono tnum">{pct(x)}</span></div>
                  ))}
                </div>
              )}
              {rep.functional && <div className="text-[12px] text-muted">Interactions <span className="font-mono text-fg">{rep.functional.interactions_passed ?? 0}/{rep.functional.interactions_total ?? 0}</span> · runtime errors <span className={cn('font-mono', errs.length ? 'text-danger' : 'text-fg')}>{errs.length}</span></div>}
            </div>
          </div>

          {errs.length > 0 && (
            <div className="mx-4 mb-3 rounded-xl border border-danger/25 bg-danger-soft p-2.5">
              <div className="mb-1 flex items-center gap-1.5 text-[12px] font-semibold text-danger"><AlertOctagon className="size-3.5" />Runtime errors</div>
              {errs.map((e, i) => <pre key={i} className="font-mono text-[12px] whitespace-pre-wrap text-fg/80">{typeof e === 'string' ? e : e.message || JSON.stringify(e)}</pre>)}
            </div>
          )}

          <div className="px-4">
            <Segmented size="xs" value={filter} onChange={setFilter} options={[{ value: 'all', label: 'All', count: checks.length }, { value: 'visual', label: 'Visual', icon: Eye, count: vis.length }, { value: 'functional', label: 'Functional', icon: MousePointerClick, count: fun.length }, { value: 'failed', label: 'Failed', count: checks.filter((c) => !c.ok).length }]} />
          </div>
          <ul className="mx-4 mt-2 mb-4 divide-y divide-line rounded-xl border border-line">
            {shown.length === 0 ? <li className="px-3 py-4 text-center text-[12px] text-subtle">No checks in this group.</li> : shown.map((c, i) => <Check1 key={(c.id || c.name) + i} c={c} i={i} />)}
          </ul>

          {repairs.length > 0 && (
            <div className="mx-4 mb-4">
              <div className="mb-2 text-[12px] font-medium tracking-wide text-subtle uppercase">Repair log</div>
              <ol className="relative space-y-3 border-l border-line pl-4">
                {repairs.map((r, i) => (
                  <li key={i} className="relative text-[12px]">
                    <span className={cn('absolute top-1 -left-[21px] size-2.5 rounded-full ring-4 ring-surface', /ok|fixed|pass|success/i.test(String(r.result)) ? 'bg-success' : 'bg-warning')} />
                    <div className="flex flex-wrap items-center gap-1.5"><Badge className="font-mono">iter {r.iteration}</Badge><span className="font-medium">{r.action}</span>{r.target && <span className="font-mono text-[12px] text-subtle">{r.target}</span>}</div>
                    <div className="mt-0.5 text-muted">{r.check}{r.result ? ` → ${r.result}` : ''}</div>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {shot && (
            <div className="mx-4 mb-4">
              <div className="mb-2 text-[12px] font-medium tracking-wide text-subtle uppercase">Validator screenshot</div>
              <a href={shot} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl border border-line bg-white"><img src={shot} alt="Validator screenshot" className="w-full" loading="lazy" /></a>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
