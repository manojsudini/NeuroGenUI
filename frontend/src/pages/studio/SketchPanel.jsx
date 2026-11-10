import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, Eraser, Grid3x3, ImagePlus, Images, MoreHorizontal, Pen, Redo2, ScanSearch, Tag, Trash2, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import { api, ApiError, errMessage } from '../../lib/api'
import { CONTAINERS, typeIcon } from '../../lib/ir'
import { cn, ms, titleCase } from '../../lib/utils'
import { Badge, Button, IconButton, Menu, MenuItem, MenuLabel, MenuSwitch, Segmented, Select, Skeleton } from '../../components/ui'
import DrawCanvas from './DrawCanvas'
import ScanOverlay from './ScanOverlay'
import { StepCard } from './parts'
import { useStudio } from './Studio'

const ASPECTS = [
  { value: 1.25, label: '4:5', title: 'Portrait (phone / form)' },
  { value: 1, label: '1:1', title: 'Square' },
  { value: 0.75, label: '4:3', title: 'Landscape (dashboard / landing)' },
]
const MODES = [
  { value: 'hybrid', label: 'Hybrid: OpenCV + vision model' },
  { value: 'cv', label: 'OpenCV only (no API key)' },
  { value: 'vision', label: 'Vision model only' },
]

function SamplePicker({ onPick }) {
  const [state, setState] = useState({ loading: true })
  useEffect(() => {
    api.samples().then((d) => setState({ data: d })).catch((e) => setState({ error: e }))
  }, [])
  return (
    <div>
      <MenuLabel>Dataset sketches</MenuLabel>
      {state.loading ? (
        <div className="grid grid-cols-3 gap-2">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="aspect-[4/5]" />)}</div>
      ) : state.error ? (
        <p className="px-2 pb-2 text-[13px] text-muted">{errMessage(state.error)}</p>
      ) : !state.data?.length ? (
        <p className="px-2 pb-2 text-[13px] text-muted">No sample sketches in the dataset yet.</p>
      ) : (
        <div className="grid max-h-80 grid-cols-3 gap-2 overflow-y-auto">
          {state.data.map((s) => (
            <button key={s.id} onClick={() => onPick(s)} className="group overflow-hidden rounded-lg border border-line bg-white text-left transition hover:border-accent">
              <img src={s.url} alt={s.title} loading="lazy" className="aspect-[4/5] w-full object-contain p-1" />
              <div className="truncate border-t border-line bg-surface px-2 py-1.5 text-[12px] text-muted">{s.title || titleCase(s.id)}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function SketchPanel() {
  const s = useStudio()
  const canvas = s.sketchRef
  const [tool, setTool] = useState('pen')
  const [width, setWidth] = useState(4)
  const [grid, setGrid] = useState(true)
  const [aspect, setAspect] = useState(1.25)
  const [, setRev] = useState(0)
  const [scanning, setScanning] = useState(false)
  const [scanKey, setScanKey] = useState(0)
  const [labels, setLabels] = useState(true)
  const [hoverIdx, setHoverIdx] = useState(null)
  const fileRef = useRef(null)
  const loadedRef = useRef(false)

  const onChange = useCallback(() => {
    setRev((n) => n + 1)
    s.setSketch((x) => ({ ...x, dirty: true }))
  }, [s.setSketch]) // eslint-disable-line react-hooks/exhaustive-deps

  const fitAspect = (a) => setAspect(Math.max(0.5, Math.min(1.8, Math.round(a * 1000) / 1000)))

  /* first paint: a sample from the URL, else the project's stored sketch */
  useEffect(() => {
    if (loadedRef.current || !canvas.current || !s.project) return
    loadedRef.current = true
    ;(async () => {
      try {
        if (s.sampleUrl) {
          fitAspect(await canvas.current.setBackground(s.sampleUrl))
          s.setAnalysis(null)
          s.clearSample()
          toast('Sample loaded on the canvas', { description: 'Analyze it, or go straight to describing it below.' })
        } else if (s.project.sketch_url) {
          fitAspect(await canvas.current.setBackground(s.project.sketch_url, { undoable: false }))
          s.setSketch((x) => ({ ...x, url: s.project.sketch_url, dirty: false }))
          setScanKey(0)
        }
      } catch (e) {
        toast.error('Could not load the sketch image', { description: e.message })
      }
    })()
  }, [s.project]) // eslint-disable-line react-hooks/exhaustive-deps

  /* keyboard: Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y, P = pen, E = eraser (ignored while typing) */
  useEffect(() => {
    const h = (e) => {
      const t = e.target
      if (t.closest?.('input, textarea, select, [contenteditable="true"], .cm-editor')) return
      const k = e.key.toLowerCase()
      if ((e.ctrlKey || e.metaKey) && k === 'z') {
        e.preventDefault()
        e.shiftKey ? canvas.current?.redo() : canvas.current?.undo()
      } else if ((e.ctrlKey || e.metaKey) && k === 'y') {
        e.preventDefault()
        canvas.current?.redo()
      } else if (!e.ctrlKey && !e.metaKey && !e.altKey && k === 'p') setTool('pen')
      else if (!e.ctrlKey && !e.metaKey && !e.altKey && k === 'e') setTool('eraser')
    }
    addEventListener('keydown', h)
    return () => removeEventListener('keydown', h)
  }, [canvas])

  const loadImage = async (src) => {
    try {
      fitAspect(await canvas.current.setBackground(src))
      s.setAnalysis(null)
      setScanKey(0)
    } catch (e) {
      toast.error('Could not load that image', { description: e.message })
    }
  }
  const onFile = (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    if (!/^image\/(png|jpe?g|webp)$/.test(f.type)) return toast.error('Use a PNG, JPG or WebP image')
    if (f.size > 12 * 1024 * 1024) return toast.error('That image is larger than 12 MB')
    loadImage(f)
  }

  const analyze = async () => {
    if (canvas.current?.isEmpty()) return toast.error('The canvas is empty', { description: 'Draw a layout, upload a photo of a sketch, or pick a sample.' })
    setScanning(true)
    try {
      const sketchId = !s.sketch.dirty && s.sketch.id ? s.sketch.id : (await s.uploadSketch()).sketch_id
      const r = await api.analyze(sketchId, s.mode)
      s.setAnalysis(r)
      setScanKey((k) => k + 1)
      const n = r.components?.length || 0
      toast.success(`Detected ${n} component${n === 1 ? '' : 's'}`, { description: `${titleCase(r.mode || s.mode)} · ${ms(r.timings?.total_ms)}` })
    } catch (e) {
      if (e instanceof ApiError && e.noKey) s.setKeyError(true)
      toast.error('Sketch analysis failed', { description: errMessage(e) })
    } finally {
      setScanning(false)
    }
  }

  const a = s.analysis
  const comps = a?.components || []
  const tally = comps.reduce((m, c) => ((m[c.type] = (m[c.type] || 0) + 1), m), {})
  const stale = s.sketch.dirty && a
  const types = Object.entries(tally).sort((x, y) => y[1] - x[1])
  const empty = canvas.current?.isEmpty?.() ?? true

  const thumb = s.sketch.url || s.project?.sketch_url
  const open = s.openStep === 'sketch'
  const summary = (
    <div className="flex items-center gap-4">
      <div className="grid h-16 w-14 shrink-0 place-items-center overflow-hidden rounded-lg border border-line bg-white">{thumb ? <img src={thumb} alt="Sketch" className="size-full object-contain p-1" /> : <Pen className="size-4 text-subtle" />}</div>
      <div className="min-w-0 flex-1 text-[13px]">
        <div className="font-medium">{comps.length ? `${comps.length} components detected` : thumb ? 'Sketch ready' : 'Nothing drawn yet'}</div>
        <div className="mt-0.5 truncate text-muted">{comps.length ? `${titleCase(a.mode || s.mode)}${a.timings?.total_ms != null ? ` · ${ms(a.timings.total_ms)}` : ''}` : 'Open to draw, upload or pick a sample'}</div>
      </div>
      <Button size="xs" variant="secondary" onClick={() => s.setOpenStep('sketch')}>Edit sketch</Button>
    </div>
  )

  return (
    <StepCard id="step-sketch" n={1} title="Sketch" open={open} onToggle={() => s.setOpenStep(open ? null : 'sketch')} summary={summary} aside={open ? (s.sketch.dirty ? <Badge>Unsaved</Badge> : s.sketch.id ? <Badge tone="success" dot>Saved</Badge> : null) : null}>
      {/* compact toolbar: drawing tools left, import + more right */}
      <div className="mb-3 flex items-center gap-1">
        <Segmented value={tool} onChange={setTool} options={[{ value: 'pen', label: '', icon: Pen, title: 'Pen (P)' }, { value: 'eraser', label: '', icon: Eraser, title: 'Eraser (E)' }]} />
        <span className="mx-1 h-5 w-px bg-line" />
        <IconButton icon={Undo2} label="Undo (Ctrl+Z)" disabled={!canvas.current?.canUndo()} onClick={() => canvas.current?.undo()} />
        <IconButton icon={Redo2} label="Redo (Ctrl+Shift+Z)" disabled={!canvas.current?.canRedo()} onClick={() => canvas.current?.redo()} />
        <div className="ml-auto flex items-center gap-1">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={onFile} />
          <IconButton icon={ImagePlus} label="Upload a sketch image" onClick={() => fileRef.current?.click()} />
          <Menu width={340} trigger={({ open, toggle }) => <IconButton icon={Images} label="Pick a sample sketch" active={open} onClick={toggle} />}>
            {(close) => <SamplePicker onPick={(x) => { close(); loadImage(x.url); if (x.instruction && !s.current) dispatchEvent(new CustomEvent('ngui:say', { detail: x.instruction })) }} />}
          </Menu>
          <Menu width={264} trigger={({ open, toggle }) => <IconButton icon={MoreHorizontal} label="Canvas options" active={open} onClick={toggle} />}>
            {(close) => (
              <>
                <MenuLabel>Paper</MenuLabel>
                <div className="px-1 pb-2"><Segmented full value={aspect} onChange={setAspect} options={ASPECTS} /></div>
                <MenuSwitch icon={Grid3x3} checked={grid} onChange={setGrid}>Grid paper</MenuSwitch>
                <MenuSwitch icon={Tag} checked={labels} onChange={setLabels}>Detection labels</MenuSwitch>
                <div className="flex h-9 items-center gap-2.5 px-2 text-[13px]">
                  <span className="grid size-4 place-items-center"><span className="rounded-full bg-fg" style={{ width: Math.min(14, width + 2), height: Math.min(14, width + 2) }} /></span>
                  <span className="flex-1">Stroke</span>
                  <input type="range" min={1} max={12} value={width} onChange={(e) => setWidth(+e.target.value)} aria-label="Stroke width" className="w-24 accent-[var(--accent)]" />
                </div>
                <div className="my-1.5 h-px bg-line" />
                <MenuItem icon={Trash2} disabled={empty} onClick={() => { canvas.current?.clear(); s.setAnalysis(null); close() }}>Clear canvas</MenuItem>
              </>
            )}
          </Menu>
        </div>
      </div>

      <div className="mx-auto" style={{ maxWidth: `max(280px, min(100%, calc((100dvh - 330px) / ${aspect})))` }}>
        <DrawCanvas ref={canvas} aspect={aspect} tool={tool} width={width} grid={grid} onChange={onChange}>
          {a && !stale && <ScanOverlay analysis={a} scanning={false} scanKey={scanKey} showLabels={labels} hoverIdx={hoverIdx} onHover={setHoverIdx} />}
          {scanning && <ScanOverlay analysis={null} scanning scanKey={0} />}
          {empty && !scanning && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center p-6 text-center">
              <div>
                <span className="mx-auto grid size-10 place-items-center rounded-full border border-line bg-surface/80"><Pen className="size-[18px] text-muted" strokeWidth={1.7} /></span>
                <p className="mt-3 text-[14px] font-medium text-muted">Draw boxes for inputs, buttons and images</p>
                <p className="mt-1 text-[13px] text-subtle">Rough labels inside help. Or upload an image, or pick a sample.</p>
              </div>
            </div>
          )}
        </DrawCanvas>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <Select size="sm" value={s.mode} onChange={(e) => s.setMode(e.target.value)} aria-label="Detection mode" wrapClass="min-w-0 flex-1">{MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}</Select>
        <Button size="sm" variant="secondary" icon={ScanSearch} loading={scanning} onClick={analyze}>{scanning ? 'Scanning' : 'Analyze'}</Button>
      </div>

      <AnimatePresence initial={false}>
        {a && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }} className="overflow-hidden">
            <div className="mt-4 rounded-xl border border-line bg-surface-2/60 p-4">
              <div className="flex items-baseline justify-between gap-3 text-[13px]">
                <span><b className="text-[15px] font-semibold tnum">{comps.length}</b> <span className="text-muted">components detected{stale ? ', sketch changed since' : ''}</span></span>
                <span className="shrink-0 font-mono text-[12px] text-subtle">{titleCase(a.mode || s.mode)}{a.timings?.total_ms != null ? ` · ${ms(a.timings.total_ms)}` : ''}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {types.slice(0, 6).map(([t, n]) => {
                  const I = typeIcon(t)
                  return <Badge key={t} tone={CONTAINERS.has(t) ? 'neutral' : 'accent'}><I className="size-3.5" />{t}<span className="font-mono opacity-70">{n}</span></Badge>
                })}
                {types.length > 6 && <Badge>+{types.length - 6}</Badge>}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <Button className="mt-4 w-full" iconRight={ArrowRight} onClick={() => s.goStep(2)}>Continue to describe</Button>
    </StepCard>
  )
}
