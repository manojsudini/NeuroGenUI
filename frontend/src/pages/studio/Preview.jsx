import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { AlertOctagon, ExternalLink, Monitor, RotateCw, Smartphone, Tablet, X } from 'lucide-react'
import { api } from '../../lib/api'
import { cn } from '../../lib/utils'
import { Badge, IconButton, Segmented } from '../../components/ui'
import { useStudio } from './Studio'

const DEVICES = {
  desktop: { w: null, h: null, label: 'Desktop', icon: Monitor },
  tablet: { w: 820, h: 1180, label: 'Tablet', icon: Tablet },
  phone: { w: 390, h: 844, label: 'Phone', icon: Smartphone },
}

/*
 * Presentation-only CSS injected into the (same-origin) preview document. The generated geometry keeps the
 * sketch's absolute offsets, which on a simple form read as huge gaps and a stretched layout. For pages that
 * only hold leaf components (heading, fields, buttons, image), this centres a comfortable column and evens out
 * the spacing. Pages with nested containers (cards, navbars, lists) are left exactly as generated.
 */
const TIDY_CSS = `
html.ngui-tidy body{background:#fff}
html.ngui-tidy .ng-app{display:flex;min-height:100vh}
html.ngui-tidy .ng-page.ng-geo{width:100%;max-width:480px !important;margin:auto !important;padding:24px 28px !important;gap:16px !important}
html.ngui-tidy .ng-page.ng-geo > *{margin:0 !important;min-width:0 !important;align-self:stretch !important;max-width:100% !important}
html.ngui-tidy .ng-page.ng-geo > .ng-btn{width:100% !important;height:44px !important}
html.ngui-tidy .ng-page.ng-geo > .ng-image{height:auto !important;aspect-ratio:16/4.5 !important}
html.ngui-tidy .ng-page.ng-geo > .ng-heading{width:auto !important;font-size:34px !important}
`
const CONTAINER_TYPES = new Set(['container', 'card', 'form', 'header', 'navbar', 'list'])

function tidy(doc) {
  if (!doc?.head) return
  if (!doc.getElementById('ngui-tidy-css')) {
    const st = doc.createElement('style')
    st.id = 'ngui-tidy-css'
    st.textContent = TIDY_CSS
    doc.head.appendChild(st)
  }
  const apply = () => {
    const page = doc.querySelector('.ng-page.ng-stack--column')
    const simple = !!page && [...page.children].every((c) => !CONTAINER_TYPES.has(c.getAttribute('data-ngtype')) && !c.classList.contains('ng-stack'))
    doc.documentElement.classList.toggle('ngui-tidy', simple)
  }
  apply()
}

function Empty() {
  const s = useStudio()
  const sk = s.sketch.url || s.project?.sketch_url
  return (
    <div className="grid size-full place-items-center p-6">
      <div className="w-full max-w-sm rounded-2xl border border-dashed border-line-strong bg-surface/70 p-6 text-center">
        <div className="mx-auto mb-5 grid w-56 grid-cols-2 gap-3">
          {sk ? <img src={sk} alt="Your sketch" className="aspect-square rounded-xl border border-line bg-white object-contain p-1" /> : <img src="/img/hands-wireframe.jpg" alt="" className="aspect-square rounded-xl border border-line object-cover" />}
          <img src="/img/designer-tablet.jpg" alt="" className="aspect-square rounded-xl border border-line object-cover" />
        </div>
        <h3 className="text-[15px] font-semibold tracking-tight">Your UI renders here</h3>
        <p className="mt-1.5 text-[13px] text-muted">Generated React runs live in a sandboxed runtime.</p>
        <ol className="mx-auto mt-4 flex max-w-[260px] flex-col gap-2 text-left text-[13px]">
          {['Sketch the layout', 'Describe the screen', 'Generate the first version'].map((t, i) => (
            <li key={t} className="flex items-center gap-2.5 text-muted"><span className="grid size-6 place-items-center rounded-full border border-line-strong text-[12px] tnum">{i + 1}</span>{t}</li>
          ))}
        </ol>
      </div>
    </div>
  )
}

export default function Preview() {
  const s = useStudio()
  const [device, setDevice] = useState('desktop')
  const [reloadKey, setReloadKey] = useState(0)
  const [loaded, setLoaded] = useState(false)
  const [showErr, setShowErr] = useState(true)
  const boxRef = useRef(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setBox({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const v = s.current
  const src = v ? api.previewUrl(s.id, v.number) : null
  useEffect(() => {
    setLoaded(false)
    s.setRuntime({ ready: false, errors: [], nodes: [], live: false })
    setShowErr(true)
  }, [src, reloadKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const d = DEVICES[device]
  const pad = 56
  const scale = d.w ? Math.min(1, (box.w - pad) / d.w, (box.h - pad) / d.h) : 1
  const errors = s.runtime.errors
  const applyTidy = () => {
    try {
      tidy(s.frameRef.current?.contentDocument)
    } catch {
      /* cross-origin: leave the preview as generated */
    }
  }
  const onLoad = () => {
    setLoaded(true)
    applyTidy()
  }
  // the runtime reports every (re)render: re-check whether the page is a simple form
  useEffect(applyTidy, [s.runtime.nodes]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-4">
        <span className="text-[14px] font-medium">Preview</span>
        {s.runtime.live && <Badge tone="warning" dot>Edited code</Badge>}
        {v && s.runtime.nodes.length > 0 && <span className="hidden text-[12px] text-subtle 2xl:inline">{s.runtime.nodes.length} nodes</span>}
        <div className="ml-auto flex items-center gap-1">
          <Segmented size="xs" value={device} onChange={setDevice} options={Object.entries(DEVICES).map(([k, x]) => ({ value: k, label: '', icon: x.icon, title: x.label }))} />
          <IconButton icon={RotateCw} label="Reload preview" size="xs" disabled={!v} onClick={() => setReloadKey((k) => k + 1)} />
          <IconButton icon={ExternalLink} label="Open in new tab" size="xs" disabled={!v} onClick={() => window.open(src, '_blank', 'noopener')} />
        </div>
      </div>

      <div ref={boxRef} className="dot-grid relative min-h-0 flex-1 overflow-hidden bg-bg-subtle">
        {!v ? (
          <Empty />
        ) : !d.w ? (
          <div className="absolute inset-4 flex flex-col overflow-hidden rounded-xl border border-line-strong bg-white shadow-card sm:inset-6">
            <div className="flex h-9 shrink-0 items-center gap-1.5 border-b border-black/10 bg-[#f4f3f0] px-3">
              {[0, 1, 2].map((i) => <span key={i} className="size-2.5 rounded-full bg-black/15" />)}
              <span className="mx-auto flex h-6 w-1/2 min-w-0 items-center justify-center truncate rounded-md bg-white/80 px-3 font-mono text-[12px] text-black/45">preview / v{v.number}</span>
              <span className="size-2.5" />
            </div>
            <div className="relative min-h-0 flex-1">
              <iframe key={`${src}-${reloadKey}`} ref={s.frameRef} src={src} title="Generated UI preview" onLoad={onLoad} className="absolute inset-0 size-full border-0 bg-white" />
              {!loaded && <div className="shimmer absolute inset-0 !rounded-none" />}
            </div>
          </div>
        ) : (
          <div className="absolute inset-0 grid place-items-center">
            <motion.div layout transition={{ type: 'spring', stiffness: 260, damping: 32 }} className="relative overflow-hidden rounded-[18px] bg-white shadow-pop ring-[7px] ring-[var(--ink)]" style={{ width: d.w * scale, height: d.h * scale }}>
              <iframe key={`${src}-${reloadKey}`} ref={s.frameRef} src={src} title="Generated UI preview" onLoad={onLoad} className="absolute top-0 left-0 border-0 bg-white" style={{ width: d.w, height: d.h, transform: `scale(${scale})`, transformOrigin: '0 0' }} />
              {!loaded && <div className="shimmer absolute inset-0 !rounded-none" />}
            </motion.div>
          </div>
        )}

        <AnimatePresence>
          {errors.length > 0 && showErr && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="absolute inset-x-4 bottom-4 z-10 max-h-[40%] overflow-y-auto rounded-xl border border-danger/30 bg-surface p-4 shadow-pop">
              <div className="mb-2 flex items-center gap-2 text-[13px] font-semibold text-danger">
                <AlertOctagon className="size-4" />Runtime error{errors.length > 1 ? `s (${errors.length})` : ''} in the preview
                <button onClick={() => setShowErr(false)} aria-label="Dismiss" className="ml-auto grid size-7 place-items-center rounded-lg text-subtle hover:bg-surface-hover hover:text-fg"><X className="size-4" /></button>
              </div>
              {errors.slice(-3).map((e, i) => (
                <pre key={i} className="mt-1.5 overflow-x-auto rounded-lg bg-danger-soft px-3 py-2 font-mono text-[12px] whitespace-pre-wrap text-fg/85">{e.message}{e.stack ? `\n${String(e.stack).split('\n').slice(0, 3).join('\n')}` : ''}</pre>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  )
}
