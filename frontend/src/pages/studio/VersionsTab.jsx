import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowLeftRight, ArrowRight, Clock, GitCompare, History, ImageOff, Mic, RotateCcw, Type, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, errMessage } from '../../lib/api'
import { KIND_LABEL, KIND_TONE, diffIr, fmtVal, typeIcon } from '../../lib/ir'
import { ago, cn, fullDate, ms } from '../../lib/utils'
import { OpChip } from '../../components/common'
import { Badge, Button, Empty, IconButton, Modal, ModalHeader, Select, Skeleton } from '../../components/ui'
import { NotGenerated, useStudio } from './Studio'

const scoreOf = (x) => x?.validation?.score ?? x?.score ?? x?.validation_score ?? null
const totalOf = (x) => x?.timings?.total ?? x?.total_ms ?? null
const shotOf = (x) => x?.validation?.screenshot_url || x?.screenshot_url || null

function Compare({ id, versions, a0, b0, onClose }) {
  const [a, setA] = useState(a0)
  const [b, setB] = useState(b0)
  const [data, setData] = useState({ loading: true })
  useEffect(() => {
    let live = true
    setData({ loading: true })
    Promise.all([api.version(id, a), api.version(id, b)])
      .then(([va, vb]) => live && setData({ va, vb, diff: diffIr(va.ir, vb.ir) }))
      .catch((e) => live && setData({ error: e }))
    return () => {
      live = false
    }
  }, [id, a, b])
  const opts = versions.map((v) => <option key={v.number} value={v.number}>v{v.number} · {KIND_LABEL[v.kind] || v.kind}</option>)
  const KTONE = { added: 'success', removed: 'danger', changed: 'warning' }
  return (
    <div>
      <ModalHeader title="Compare versions" desc="Validator screenshots side by side, and every IR node that changed." onClose={onClose} />
      <div className="flex items-center gap-2 px-5 pt-4">
        <Select size="sm" value={a} onChange={(e) => setA(+e.target.value)}>{opts}</Select>
        <IconButton icon={ArrowLeftRight} label="Swap" size="sm" onClick={() => { setA(b); setB(a) }} />
        <Select size="sm" value={b} onChange={(e) => setB(+e.target.value)}>{opts}</Select>
      </div>
      {data.loading ? (
        <div className="grid grid-cols-2 gap-3 p-5"><Skeleton className="aspect-[4/5]" /><Skeleton className="aspect-[4/5]" /></div>
      ) : data.error ? (
        <p className="p-5 text-[13px] text-danger">{errMessage(data.error)}</p>
      ) : (
        <div className="p-5">
          <div className="grid grid-cols-2 gap-3">
            {[data.va, data.vb].map((v, i) => (
              <figure key={i} className="min-w-0">
                <figcaption className="mb-1.5 flex items-center gap-1.5 text-[12px]"><Badge tone={i ? 'accent' : 'neutral'} className="font-mono">{i ? 'after' : 'before'} · v{v.number}</Badge><span className="truncate text-muted">{v.text || KIND_LABEL[v.kind]}</span></figcaption>
                <div className="aspect-[4/3] overflow-hidden rounded-xl border border-line bg-white">
                  {shotOf(v) ? <img src={shotOf(v)} alt={`Version ${v.number}`} className="size-full object-contain object-top" /> : <div className="grid size-full place-items-center text-[12px] text-subtle"><span className="flex flex-col items-center gap-1"><ImageOff className="size-5" />No screenshot</span></div>}
                </div>
              </figure>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between text-[13px]">
            <span className="font-semibold">IR changes</span>
            <span className="text-muted">{data.diff.changes.length} changed · {data.diff.unchanged} untouched</span>
          </div>
          {data.diff.changes.length === 0 ? (
            <p className="mt-2 rounded-xl border border-line px-3 py-4 text-center text-[13px] text-subtle">The two IR trees are identical.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line rounded-xl border border-line">
              {data.diff.changes.map((c) => {
                const I = typeIcon(c.type)
                return (
                  <li key={c.id + c.kind} className="px-3 py-2 text-[12px]">
                    <div className="flex items-center gap-1.5"><Badge tone={KTONE[c.kind]} >{c.kind}</Badge><I className="size-3.5 text-muted" /><span className="font-medium">{c.type}</span>{c.label && <span className="truncate text-muted">“{c.label}”</span>}<span className="ml-auto font-mono text-[12px] text-subtle">{c.id}</span></div>
                    {c.fields.map((f) => (
                      <div key={f.f} className="mt-1 flex flex-wrap items-center gap-1.5 pl-1 font-mono text-[12px]">
                        <span className="text-subtle">{f.f}</span>
                        <span className="rounded bg-danger-soft px-1 text-danger line-through decoration-danger/50">{fmtVal(f.from)}</span>
                        <ArrowRight className="size-3 text-subtle" />
                        <span className="rounded bg-success-soft px-1 text-success">{fmtVal(f.to)}</span>
                      </div>
                    ))}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export default function VersionsTab() {
  const s = useStudio()
  const [busy, setBusy] = useState(null)
  const [cmp, setCmp] = useState(null)
  if (!s.current && !s.versions.length) return <NotGenerated what="The version history" />
  const list = s.versions
  const latest = list[0]?.number

  const restore = async (n) => {
    setBusy(n)
    try {
      s.adopt(await api.restore(s.id, n), `Restored v${n}`)
    } catch (e) {
      toast.error('Restore failed', { description: errMessage(e) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-4">
        <span className="text-[12px] text-muted">{list.length} version{list.length === 1 ? '' : 's'} · newest first</span>
        <Button size="xs" variant="secondary" icon={GitCompare} className="ml-auto" disabled={list.length < 2} onClick={() => { const b = s.current?.number ?? latest; const a = s.current?.parent ?? list.find((x) => x.number < b)?.number ?? list[list.length - 1].number; setCmp({ a, b }) }}>Compare</Button>
      </div>
      {!list.length ? (
        <Empty compact icon={History} title="Loading history…" />
      ) : (
        <ol className="min-h-0 flex-1 overflow-y-auto p-4">
          {list.map((x, i) => {
            const active = s.current?.number === x.number
            const score = scoreOf(x)
            const total = totalOf(x)
            const ops = Array.isArray(x.ops) ? x.ops : []
            return (
              <motion.li key={x.number} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 10) * 0.03 }} className="relative pb-4 pl-9">
                {i < list.length - 1 && <span className="absolute top-8 bottom-0 left-[11.5px] w-px bg-line" />}
                <span className={cn('absolute top-2 left-0 grid size-6 place-items-center rounded-full border-2 font-mono text-[12px] font-medium', active ? 'border-accent bg-accent text-accent-fg' : 'border-line-strong bg-surface text-muted')}>{x.number}</span>
                <div role="button" tabIndex={0} onClick={() => s.selectVersion(x.number)} onKeyDown={(e) => e.key === 'Enter' && s.selectVersion(x.number)} className={cn('cursor-pointer rounded-xl border p-4 transition-colors', active ? 'border-accent/50 bg-accent-soft/40 ring-4 ring-accent/10' : 'border-line hover:border-line-strong hover:bg-surface-hover/50')}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={KIND_TONE[x.kind] || 'neutral'} >{KIND_LABEL[x.kind] || x.kind}</Badge>
                    {x.source && x.kind !== 'restore' && (x.kind === 'generate' || x.kind === 'modify') && <span className="flex items-center gap-1 text-[12px] text-subtle">{x.source === 'voice' ? <Mic className="size-3 text-accent" /> : <Type className="size-3" />}{x.source}</span>}
                    {x.number === latest && <Badge tone="solid" >latest</Badge>}
                    {score != null && <Badge tone={score >= 0.85 ? 'success' : score >= 0.6 ? 'warning' : 'danger'} className="ml-auto h-5 font-mono text-[12px]">{Math.round(score * 100)}%</Badge>}
                  </div>
                  {x.text && <p className="mt-2 text-[13px] leading-snug">“{x.text}”</p>}
                  {ops.length > 0 && <div className="mt-3 flex flex-col items-start gap-2">{ops.slice(0, 3).map((o, j) => <OpChip key={j} op={o} />)}{ops.length > 3 && <span className="text-[12px] text-subtle">+{ops.length - 3} more ops</span>}</div>}
                  {!ops.length && (typeof x.changes === 'number' || typeof x.repairs === 'number') && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {typeof x.changes === 'number' && x.changes > 0 && <Badge >{x.changes} change{x.changes === 1 ? '' : 's'}{x.changes_ok != null && x.changes_ok < x.changes ? ` · ${x.changes - x.changes_ok} failed` : ''}</Badge>}
                      {typeof x.repairs === 'number' && x.repairs > 0 && <Badge tone="warning" >{x.repairs} repair{x.repairs === 1 ? '' : 's'}</Badge>}
                      {x.ir_synced === false && <Badge tone="warning" >IR not synced</Badge>}
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-subtle">
                    <span title={fullDate(x.created_at)} className="flex items-center gap-1"><Clock className="size-3" />{ago(x.created_at)}</span>
                    {total != null && <span className="font-mono">{ms(total)}</span>}
                    <span className="ml-auto flex gap-1">
                      {x.parent != null && <button onClick={(e) => { e.stopPropagation(); setCmp({ a: x.parent, b: x.number }) }} className="rounded px-1.5 py-0.5 font-medium text-muted hover:bg-surface-hover hover:text-fg">Diff</button>}
                      {x.number !== latest && <button disabled={busy != null} onClick={(e) => { e.stopPropagation(); restore(x.number) }} className="flex items-center gap-1 rounded px-1.5 py-0.5 font-medium text-accent hover:bg-accent-soft disabled:opacity-50"><RotateCcw className="size-3" />{busy === x.number ? 'Restoring…' : 'Restore'}</button>}
                    </span>
                  </div>
                </div>
              </motion.li>
            )
          })}
        </ol>
      )}
      <Modal open={!!cmp} onClose={() => setCmp(null)} className="max-w-3xl">
        <AnimatePresence>{cmp && <Compare id={s.id} versions={list} a0={cmp.a} b0={cmp.b} onClose={() => setCmp(null)} />}</AnimatePresence>
      </Modal>
    </div>
  )
}
