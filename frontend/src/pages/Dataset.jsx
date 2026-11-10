import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { Database, Eye, EyeOff, FileAudio, Images, Pause, Play, Search, X } from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/store'
import { CONTAINERS, OP_TONE, typeIcon } from '../lib/ir'
import { cn, titleCase } from '../lib/utils'
import { Badge, Card, Empty, ErrorState, IconButton, Input, Modal, PageHeader, Segmented, Skeleton, Switch, stagger } from '../components/ui'

const labelCache = new Map()
function useLabels(url, enabled) {
  const [data, setData] = useState(() => labelCache.get(url) || null)
  useEffect(() => {
    if (!enabled || !url || labelCache.has(url)) {
      if (labelCache.has(url)) setData(labelCache.get(url))
      return
    }
    let live = true
    api.json(url).then((d) => {
      labelCache.set(url, d)
      if (live) setData(d)
    }).catch(() => {})
    return () => {
      live = false
    }
  }, [url, enabled])
  return data
}

function GtBoxes({ labels, dense }) {
  if (!labels?.components) return null
  return (
    <div className="pointer-events-none absolute inset-0">
      {labels.components.map((c, i) => {
        const b = c.bbox
        if (!b) return null
        const container = CONTAINERS.has(c.type)
        return (
          <motion.div key={i} initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.02, duration: 0.3 }} className={cn('absolute rounded-[3px] border', container ? 'border-dashed border-fg/40' : 'border-accent bg-accent/[0.07]')} style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }}>
            {!dense && !container && <span className="absolute -top-[15px] left-0 rounded-sm bg-accent px-1 text-[9px] leading-[13px] font-medium whitespace-nowrap text-accent-fg">{c.type}</span>}
          </motion.div>
        )
      })}
    </div>
  )
}

function SketchCard({ s, i, showGt, onOpen }) {
  const [hover, setHover] = useState(false)
  const [ar, setAr] = useState(null)
  const labels = useLabels(s.labels_url, showGt || hover)
  return (
    <motion.button {...stagger(i, 0.02)} onClick={() => onOpen(s)} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} className="group overflow-hidden rounded-2xl border border-line bg-surface text-left transition-[box-shadow,border-color] hover:border-line-strong hover:shadow-card">
      <div className="grid aspect-[4/3] place-items-center overflow-hidden bg-white p-2">
        <div className="relative max-h-full max-w-full" style={ar ? { aspectRatio: ar, width: ar >= 4 / 3 ? '100%' : 'auto', height: ar >= 4 / 3 ? 'auto' : '100%' } : { width: '100%' }}>
          <img src={s.url} alt={s.id} loading="lazy" onLoad={(e) => setAr(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)} className="block size-full" />
          {(showGt || hover) && ar && <GtBoxes labels={labels} dense />}
        </div>
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-line px-3 py-2">
        <span className="truncate font-mono text-[12px]">{s.id}</span>
        <span className="shrink-0 text-[12px] text-subtle">{s.n_components ?? '—'} comp.</span>
      </div>
    </motion.button>
  )
}

function SketchDetail({ s, onClose }) {
  const labels = useLabels(s?.labels_url, !!s)
  if (!s) return null
  const tally = (labels?.components || []).reduce((m, c) => ((m[c.type] = (m[c.type] || 0) + 1), m), {})
  return (
    <div className="grid gap-0 md:grid-cols-[1fr_300px]">
      <div className="relative bg-white p-6">
        <div className="relative mx-auto max-w-[460px]">
          <img src={s.url} alt={s.id} className="w-full" />
          <GtBoxes labels={labels} />
        </div>
      </div>
      <div className="border-l border-line p-5">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-mono text-[13px] font-semibold">{s.id}</div>
            <Badge className="mt-1">{titleCase(s.category)}</Badge>
          </div>
          <IconButton icon={X} label="Close" size="sm" onClick={onClose} />
        </div>
        {!labels ? (
          <div className="mt-4 space-y-2"><Skeleton className="h-4" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-20" /></div>
        ) : (
          <>
            {labels.instruction && (
              <div className="mt-4">
                <div className="text-[12px] font-medium tracking-wide text-subtle uppercase">Generate instruction</div>
                <p className="mt-1 text-[13px] leading-relaxed">“{labels.instruction}”</p>
              </div>
            )}
            <div className="mt-4 text-[12px] font-medium tracking-wide text-subtle uppercase">Ground truth · {labels.components?.length || 0}</div>
            <div className="mt-1.5 flex flex-wrap gap-1">
              {Object.entries(tally).map(([t, n]) => {
                const I = typeIcon(t)
                return <Badge key={t} tone={CONTAINERS.has(t) ? 'neutral' : 'accent'} ><I className="size-3" />{t} <span className="font-mono opacity-70">{n}</span></Badge>
              })}
            </div>
            {labels.interactions?.length > 0 && (
              <>
                <div className="mt-4 text-[12px] font-medium tracking-wide text-subtle uppercase">Interactions</div>
                <ul className="mt-1.5 space-y-1 text-[12px] text-muted">{labels.interactions.map((x, i) => <li key={i}>on <b className="font-medium text-fg">{x.event}</b> of “{x.target_label}” → {x.expect}</li>)}</ul>
              </>
            )}
            {labels.synthetic && <p className="mt-4 text-[12px] text-subtle">Synthetic sketch{labels.generator ? ` · ${labels.generator}` : ''}. Labels come from the generator, not hand annotation.</p>}
          </>
        )}
      </div>
    </div>
  )
}

function AudioButton({ url, playing, onToggle }) {
  if (!url) return <span className="text-[12px] text-subtle">—</span>
  return <IconButton icon={playing ? Pause : Play} label={playing ? 'Pause' : 'Play the voice command'} size="sm" active={playing} onClick={onToggle} />
}

export default function Dataset() {
  const d = useAsync(() => api.dataset(), [])
  const [cat, setCat] = useState('all')
  const [showGt, setShowGt] = useState(false)
  const [open, setOpen] = useState(null)
  const [ccat, setCcat] = useState('all')
  const [q, setQ] = useState('')
  const [playing, setPlaying] = useState(null)
  const [limit, setLimit] = useState(25)
  const audio = useRef(null)
  useEffect(() => () => audio.current?.pause(), [])

  const sketches = d.data?.sketches || []
  const commands = d.data?.commands || []
  const cats = useMemo(() => [...new Set(sketches.map((s) => s.category))].sort(), [sketches])
  const ccats = useMemo(() => [...new Set(commands.map((c) => c.category))].sort(), [commands])
  const shownSketches = sketches.filter((s) => cat === 'all' || s.category === cat)
  const shownCmds = commands.filter((c) => (ccat === 'all' || c.category === ccat) && (c.text + c.id).toLowerCase().includes(q.trim().toLowerCase()))

  const toggleAudio = (c) => {
    if (playing === c.id) {
      audio.current?.pause()
      setPlaying(null)
      return
    }
    audio.current?.pause()
    const a = new Audio(c.audio_url)
    audio.current = a
    a.onended = () => setPlaying(null)
    a.onerror = () => setPlaying(null)
    a.play().catch(() => setPlaying(null))
    setPlaying(c.id)
  }

  return (
    <div>
      <PageHeader eyebrow="Evaluation set" title="Dataset" desc="The test sketches with their ground-truth components, and the voice commands used to measure refinement. All of it is synthetic and generated reproducibly; see dataset/README.md." actions={d.data && <><Badge><Images className="size-3" />{sketches.length} sketches</Badge><Badge><FileAudio className="size-3" />{commands.length} commands</Badge></>} />

      {d.loading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="aspect-[4/5] rounded-2xl" />)}</div>
      ) : d.error ? (
        <Card><ErrorState error={d.error} onRetry={d.reload} /></Card>
      ) : !sketches.length && !commands.length ? (
        <Card><Empty image="/img/wireframes-paper.jpg" title="The dataset hasn’t been generated yet" desc="Once dataset/sketches, labels and commands exist, they show up here with their ground truth." /></Card>
      ) : (
        <>
          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div className="-mx-4 max-w-[calc(100%+2rem)] overflow-x-auto px-4 no-scrollbar sm:mx-0 sm:max-w-full sm:px-0">
                <Segmented size="sm" value={cat} onChange={setCat} options={[{ value: 'all', label: 'All', count: sketches.length }, ...cats.map((c) => ({ value: c, label: titleCase(c), count: sketches.filter((s) => s.category === c).length }))]} />
              </div>
              <label className="flex items-center gap-2 text-[13px] text-muted">{showGt ? <Eye className="size-4" /> : <EyeOff className="size-4" />}Ground truth boxes<Switch checked={showGt} onChange={setShowGt} label="Show ground truth" /></label>
            </div>
            {shownSketches.length ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{shownSketches.map((s, i) => <SketchCard key={s.id} s={s} i={i} showGt={showGt} onOpen={setOpen} />)}</div>
            ) : (
              <Card><Empty compact icon={Images} title="No sketches in this category" /></Card>
            )}
            <p className="mt-2 text-[12px] text-subtle">Hover a sketch to overlay its labelled boxes. Click for details.</p>
          </section>

          <section className="mt-10">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-[16px] font-semibold tracking-tight">Voice commands</h2>
                <p className="text-[13px] text-muted">Each command has an expected op and a machine-checkable postcondition. Audio is TTS, transcribed by Whisper during evaluation.</p>
              </div>
              <Input icon={Search} size="sm" placeholder="Search commands" value={q} onChange={(e) => setQ(e.target.value)} wrapClass="w-full sm:w-60" />
            </div>
            <div className="-mx-4 mb-3 overflow-x-auto px-4 no-scrollbar sm:mx-0 sm:px-0">
              <Segmented size="sm" value={ccat} onChange={setCcat} options={[{ value: 'all', label: 'All', count: commands.length }, ...ccats.map((c) => ({ value: c, label: titleCase(c), count: commands.filter((x) => x.category === c).length }))]} />
            </div>
            <Card className="overflow-hidden">
              {shownCmds.length === 0 ? (
                <Empty compact icon={Database} title="No commands match" />
              ) : (
                <>
                <ul className="divide-y divide-line md:hidden">
                  {shownCmds.slice(0, limit).map((c) => (
                    <li key={c.id} className={cn('flex gap-3 px-4 py-3', playing === c.id && 'bg-accent-soft/40')}>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5"><span className="font-mono text-[12px] text-muted">{c.id}</span><Badge tone={OP_TONE[c.category] || 'neutral'} >{c.category}</Badge>{c.sketch_id && <span className="font-mono text-[12px] text-subtle">{c.sketch_id}</span>}</div>
                        <p className="mt-1 text-[13px]">“{c.text}”</p>
                        <p className="mt-0.5 text-[12px] text-muted"><span className="font-mono font-medium text-fg">{c.expected?.op}</span>{(c.expected?.target_ref || c.expected?.target_id) && ` · ${c.expected.target_ref || c.expected.target_id}`}</p>
                      </div>
                      <AudioButton url={c.audio_url} playing={playing === c.id} onToggle={() => toggleAudio(c)} />
                    </li>
                  ))}
                </ul>
                <div className="hidden overflow-x-auto md:block">
                  <table className="w-full text-left text-[13px]">
                    <thead className="border-b border-line bg-surface-2/60 text-[12px] text-subtle uppercase">
                      <tr><th className="px-4 py-2.5 font-medium">ID</th><th className="px-3 py-2.5 font-medium">Category</th><th className="px-3 py-2.5 font-medium">Command</th><th className="px-3 py-2.5 font-medium">Expected</th><th className="px-3 py-2.5 font-medium">Sketch</th><th className="w-12 px-3 py-2.5 font-medium">Audio</th></tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {shownCmds.slice(0, limit).map((c) => (
                        <tr key={c.id} className={cn('transition-colors hover:bg-surface-hover/60', playing === c.id && 'bg-accent-soft/40')}>
                          <td className="px-4 py-2.5 font-mono text-[12px] text-muted">{c.id}</td>
                          <td className="px-3 py-2.5"><Badge tone={OP_TONE[c.category] || 'neutral'}>{c.category}</Badge></td>
                          <td className="px-3 py-2.5">“{c.text}”</td>
                          <td className="px-3 py-2.5 text-[12px]"><span className="font-mono font-medium">{c.expected?.op}</span>{(c.expected?.target_ref || c.expected?.target_id) && <span className="text-muted"> · {c.expected.target_ref || c.expected.target_id}</span>}</td>
                          <td className="px-3 py-2.5 font-mono text-[12px] text-subtle">{c.sketch_id || '—'}</td>
                          <td className="px-3 py-1.5"><AudioButton url={c.audio_url} playing={playing === c.id} onToggle={() => toggleAudio(c)} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {shownCmds.length > limit && (
                  <div className="border-t border-line p-2 text-center">
                    <button onClick={() => setLimit(1e9)} className="rounded-lg px-3 py-1.5 text-[13px] font-medium text-accent hover:bg-accent-soft">Show all {shownCmds.length} commands</button>
                  </div>
                )}
                </>
              )}
            </Card>
          </section>
        </>
      )}

      <Modal open={!!open} onClose={() => setOpen(null)} className="max-w-4xl">
        <SketchDetail s={open} onClose={() => setOpen(null)} />
      </Modal>
    </div>
  )
}
