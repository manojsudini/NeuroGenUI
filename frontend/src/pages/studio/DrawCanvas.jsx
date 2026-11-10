import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { cn } from '../../lib/utils'

/*
 * Freehand sketch canvas.
 * - Pointer events (mouse, pen, touch), pressure-insensitive, pointer capture, touch-action: none.
 * - Strokes are stored in width-normalised units (x 0..1, y 0..aspect) so they survive resizes and export at 1000px.
 * - Smoothing: quadratic curves through the midpoints of consecutive samples.
 * - History is a stack of immutable {strokes, bg} snapshots → undo / redo / clear are all undoable.
 */
const EXPORT_W = 1000

function tracePath(ctx, pts, scale) {
  ctx.beginPath()
  if (pts.length === 1) {
    ctx.arc(pts[0][0] * scale, pts[0][1] * scale, ctx.lineWidth / 2, 0, Math.PI * 2)
    ctx.fillStyle = ctx.strokeStyle
    ctx.fill()
    return false
  }
  ctx.moveTo(pts[0][0] * scale, pts[0][1] * scale)
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = ((pts[i][0] + pts[i + 1][0]) / 2) * scale
    const my = ((pts[i][1] + pts[i + 1][1]) / 2) * scale
    ctx.quadraticCurveTo(pts[i][0] * scale, pts[i][1] * scale, mx, my)
  }
  const last = pts[pts.length - 1]
  ctx.lineTo(last[0] * scale, last[1] * scale)
  return true
}
function drawStroke(ctx, s, scale, ink) {
  ctx.save()
  ctx.globalCompositeOperation = s.tool === 'eraser' ? 'destination-out' : 'source-over'
  ctx.strokeStyle = s.tool === 'eraser' ? '#000' : ink
  ctx.lineWidth = (s.w / EXPORT_W) * scale
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  if (tracePath(ctx, s.pts, scale)) ctx.stroke()
  ctx.restore()
}
function drawBg(ctx, img, w, h) {
  if (!img) return
  const r = Math.min(w / img.naturalWidth, h / img.naturalHeight)
  const dw = img.naturalWidth * r
  const dh = img.naturalHeight * r
  ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh)
}
const inkColor = () => getComputedStyle(document.documentElement).getPropertyValue('--ink').trim() || '#1f1d1a'

const DrawCanvas = forwardRef(function DrawCanvas({ aspect = 1.25, tool = 'pen', width = 4, grid = true, onChange, children, className }, ref) {
  const wrapRef = useRef(null)
  const canvasRef = useRef(null)
  const cacheRef = useRef(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [state, setState] = useState({ strokes: [], bg: null })
  const hist = useRef({ past: [], future: [] })
  const live = useRef(null)

  const stateRef = useRef(state)
  const apply = (next) => {
    stateRef.current = next
    setState(next)
  }
  const commit = useCallback(
    (next) => {
      const cur = stateRef.current
      const n = typeof next === 'function' ? next(cur) : next
      hist.current.past.push(cur)
      if (hist.current.past.length > 200) hist.current.past.shift()
      hist.current.future = []
      apply(n)
      onChange?.()
    },
    [onChange],
  )

  /* size follows the container width */
  useEffect(() => {
    const el = wrapRef.current
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth
      setSize({ w, h: Math.round(w * aspect) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [aspect])

  /* re-render committed strokes into an offscreen cache, then blit */
  const paint = useCallback(() => {
    const c = canvasRef.current
    if (!c || !size.w) return
    const dpr = Math.min(devicePixelRatio || 1, 2)
    const W = Math.round(size.w * dpr)
    const H = Math.round(size.h * dpr)
    if (c.width !== W || c.height !== H) {
      c.width = W
      c.height = H
    }
    let cache = cacheRef.current
    if (!cache) cache = cacheRef.current = document.createElement('canvas')
    cache.width = W
    cache.height = H
    const cc = cache.getContext('2d')
    cc.clearRect(0, 0, W, H)
    drawBg(cc, state.bg, W, H)
    const ink = inkColor()
    for (const s of state.strokes) drawStroke(cc, s, W, ink)
    const ctx = c.getContext('2d')
    ctx.clearRect(0, 0, W, H)
    ctx.drawImage(cache, 0, 0)
  }, [size, state])
  useEffect(() => {
    paint()
  }, [paint])
  /* theme switch changes the ink colour */
  useEffect(() => {
    const mo = new MutationObserver(() => paint())
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [paint])

  const drawLive = () => {
    const c = canvasRef.current
    const s = live.current
    if (!c || !s) return
    const ctx = c.getContext('2d')
    ctx.clearRect(0, 0, c.width, c.height)
    ctx.drawImage(cacheRef.current, 0, 0)
    drawStroke(ctx, s, c.width, inkColor())
  }

  const toPoint = (e) => {
    const r = canvasRef.current.getBoundingClientRect()
    return [(e.clientX - r.left) / r.width, ((e.clientY - r.top) / r.width)]
  }
  const onDown = (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    e.preventDefault()
    canvasRef.current.setPointerCapture(e.pointerId)
    const w = tool === 'eraser' ? width * 4 + 10 : width
    live.current = { tool, w: (w / size.w) * EXPORT_W, pts: [toPoint(e)], id: e.pointerId }
    drawLive()
  }
  const onMove = (e) => {
    const s = live.current
    if (!s || s.id !== e.pointerId) return
    const evs = e.nativeEvent.getCoalescedEvents?.() || [e]
    for (const ev of evs) {
      const p = toPoint(ev)
      const q = s.pts[s.pts.length - 1]
      if (Math.hypot(p[0] - q[0], p[1] - q[1]) * size.w >= 1.2) s.pts.push(p)
    }
    drawLive()
  }
  const onUp = (e) => {
    const s = live.current
    if (!s || s.id !== e.pointerId) return
    live.current = null
    const { id: _id, ...stroke } = s // eslint-disable-line no-unused-vars
    commit((cur) => ({ ...cur, strokes: [...cur.strokes, stroke] }))
  }

  useImperativeHandle(
    ref,
    () => ({
      undo() {
        const h = hist.current
        if (!h.past.length) return
        h.future.push(stateRef.current)
        apply(h.past.pop())
        onChange?.()
      },
      redo() {
        const h = hist.current
        if (!h.future.length) return
        h.past.push(stateRef.current)
        apply(h.future.pop())
        onChange?.()
      },
      clear() {
        commit({ strokes: [], bg: null })
      },
      canUndo: () => hist.current.past.length > 0,
      canRedo: () => hist.current.future.length > 0,
      isEmpty: () => state.strokes.length === 0 && !state.bg,
      strokeCount: () => state.strokes.length,
      /** Load an image (upload / sample / stored sketch) as the paper. Returns its aspect (h/w). */
      async setBackground(src, { undoable = true } = {}) {
        const img = new Image()
        img.decoding = 'async'
        if (typeof src !== 'string') src = URL.createObjectURL(src)
        await new Promise((res, rej) => {
          img.onload = res
          img.onerror = () => rej(new Error('Could not load that image'))
          img.src = src
        })
        const next = { strokes: [], bg: img }
        if (undoable) commit(next)
        else {
          hist.current = { past: [], future: [] }
          apply(next)
        }
        return img.naturalHeight / img.naturalWidth
      },
      /** PNG at 1000px wide, black ink on white: what the backend analyses. */
      getBlob() {
        if (state.strokes.length === 0 && !state.bg) return Promise.resolve(null)
        const W = EXPORT_W
        const H = Math.round(EXPORT_W * aspect)
        const layer = document.createElement('canvas')
        layer.width = W
        layer.height = H
        const lc = layer.getContext('2d')
        drawBg(lc, state.bg, W, H)
        for (const s of state.strokes) drawStroke(lc, s, W, '#111111')
        const out = document.createElement('canvas')
        out.width = W
        out.height = H
        const oc = out.getContext('2d')
        oc.fillStyle = '#ffffff'
        oc.fillRect(0, 0, W, H)
        oc.drawImage(layer, 0, 0)
        return new Promise((res) => out.toBlob(res, 'image/png'))
      },
    }),
    [state, aspect, commit, onChange],
  )

  return (
    <div ref={wrapRef} className={cn('relative w-full overflow-hidden rounded-xl border border-line', grid ? 'paper-grid' : 'paper-plain', className)} style={{ height: size.h || undefined, aspectRatio: size.h ? undefined : `1 / ${aspect}` }}>
      <canvas
        ref={canvasRef}
        aria-label="Sketch canvas: draw with mouse, pen or finger"
        role="img"
        className={cn('absolute inset-0 size-full touch-none select-none', tool === 'eraser' ? 'cursor-cell' : 'cursor-crosshair')}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onContextMenu={(e) => e.preventDefault()}
      />
      {children}
    </div>
  )
})

export default DrawCanvas
