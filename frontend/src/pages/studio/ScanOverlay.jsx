import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { CONTAINERS, typeIcon } from '../../lib/ir'
import { cn } from '../../lib/utils'

const EASE = [0.16, 1, 0.3, 1]

/**
 * Signature moment #1: a scan line sweeps the paper, then every detected component
 * draws its box in, one by one, with a type + label chip and its confidence.
 */
export default function ScanOverlay({ analysis, scanning, scanKey, showLabels = true, hoverIdx, onHover }) {
  const ref = useRef(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    const ro = new ResizeObserver(() => setBox({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const comps = (analysis?.components || []).filter((c) => c?.bbox)
  // big containers first so leaf boxes are drawn on top
  const order = comps.map((c, i) => ({ c, i })).sort((a, b) => b.c.bbox.w * b.c.bbox.h - a.c.bbox.w * a.c.bbox.h)
  const sweep = 0.9

  // greedy chip placement: above the box, else inside it, nudged right/down until it no longer overlaps a placed chip
  const placed = []
  const chipPos = {}
  if (box.w > 0) {
    for (const { c, i } of [...order].sort((a, b) => a.c.bbox.y - b.c.bbox.y)) {
      const container = CONTAINERS.has(c.type)
      const text = `${c.type}${c.label && !container ? ` · ${c.label}` : ''} 00`
      const w = Math.min(box.w * 0.7, 26 + text.length * 5.4)
      const h = 17
      const bx = c.bbox.x * box.w
      const by = c.bbox.y * box.h
      const cands = [[bx, by - h - 2], [bx + 2, by + 2], [bx, by + c.bbox.h * box.h + 2]]
      let best = null
      for (const [x0, y0] of cands) {
        for (let dx = 0; dx < box.w; dx += 24) {
          const x = Math.min(x0 + dx, box.w - w - 2)
          const y = Math.max(0, Math.min(y0, box.h - h))
          const hit = placed.some((r) => x < r.x + r.w && x + w > r.x && y < r.y + r.h && y + h > r.y)
          if (!hit) { best = { x, y, w, h }; break }
          if (x >= box.w - w - 2) break
        }
        if (best) break
      }
      best ||= { x: Math.min(bx, box.w - w - 2), y: Math.max(0, by - h - 2), w, h }
      placed.push(best)
      chipPos[i] = best
    }
  }

  return (
    <div ref={ref} className="pointer-events-none absolute inset-0">
      {/* scan line: loops while the request runs, sweeps once when results land */}
      <AnimatePresence>
        {scanning && (
          <motion.div key="loop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 overflow-hidden">
            <div className="absolute inset-0 bg-accent/[0.04]" />
            <motion.div className="absolute inset-x-0 h-16" style={{ background: 'linear-gradient(to bottom, transparent, color-mix(in oklab, var(--accent) 16%, transparent))' }} initial={{ top: '-64px' }} animate={{ top: '100%' }} transition={{ duration: 1.6, ease: 'easeInOut', repeat: Infinity }}>
              <div className="absolute inset-x-0 bottom-0 h-[2px] bg-accent shadow-[0_0_12px_var(--accent)]" />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      {!scanning && scanKey > 0 && comps.length > 0 && (
        <motion.div key={`sweep-${scanKey}`} className="absolute inset-x-0 h-[2px] bg-accent shadow-[0_0_12px_var(--accent)]" initial={{ top: 0, opacity: 1 }} animate={{ top: '100%', opacity: [1, 1, 0] }} transition={{ duration: sweep, ease: EASE }} />
      )}

      {box.w > 0 && (
        <svg key={`boxes-${scanKey}`} width={box.w} height={box.h} className="absolute inset-0 overflow-visible">
          {order.map(({ c, i }, k) => {
            const x = c.bbox.x * box.w
            const y = c.bbox.y * box.h
            const w = Math.max(4, c.bbox.w * box.w)
            const h = Math.max(4, c.bbox.h * box.h)
            const container = CONTAINERS.has(c.type)
            const delay = scanKey > 0 ? sweep * (c.bbox.y + c.bbox.h / 2) * 0.9 + k * 0.035 : 0
            const hot = hoverIdx === i
            return (
              <motion.path
                key={i}
                d={`M${x} ${y}h${w}v${h}h${-w}Z`}
                fill={hot ? 'color-mix(in oklab, var(--accent) 12%, transparent)' : container ? 'transparent' : 'color-mix(in oklab, var(--accent) 5%, transparent)'}
                stroke={container ? 'var(--fg-muted)' : 'var(--accent)'}
                strokeWidth={hot ? 2.5 : container ? 1.25 : 1.75}
                strokeDasharray={container ? '5 4' : undefined}
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ pathLength: { duration: 0.55, delay, ease: EASE }, opacity: { duration: 0.1, delay } }}
              />
            )
          })}
        </svg>
      )}

      {box.w > 0 && showLabels && (
        <div key={`chips-${scanKey}`} className="absolute inset-0">
          {order.map(({ c, i }, k) => {
            const container = CONTAINERS.has(c.type)
            const Icon = typeIcon(c.type)
            const pos = chipPos[i]
            const delay = scanKey > 0 ? sweep * (c.bbox.y + c.bbox.h / 2) * 0.9 + k * 0.035 + 0.25 : 0
            const conf = c.confidence != null ? Math.round(c.confidence * 100) : null
            return (
              <motion.button
                type="button"
                key={i}
                onMouseEnter={() => onHover?.(i)}
                onMouseLeave={() => onHover?.(null)}
                initial={{ opacity: 0, y: 4, scale: 0.94 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.35, delay, ease: EASE }}
                className={cn(
                  'pointer-events-auto absolute flex max-w-[70%] items-center gap-1 rounded-md px-1.5 py-[2px] text-[12px] leading-none font-medium whitespace-nowrap shadow-xs',
                  container ? 'border border-line bg-surface text-muted' : 'bg-accent text-accent-fg',
                  hoverIdx === i && 'z-10 ring-2 ring-accent/40',
                )}
                style={{ left: pos.x, top: pos.y, maxWidth: pos.w + 8 }}
                title={`${c.type}${c.label ? ` · ${c.label}` : ''}${conf != null ? ` · ${conf}%` : ''}${c.source ? ` · ${c.source}` : ''}`}
              >
                <Icon className="size-3 shrink-0" strokeWidth={2.2} />
                <span className="shrink-0">{c.type}</span>
                {c.label && !container && <span className="truncate opacity-85">· {c.label}</span>}
                {conf != null && <span className="shrink-0 font-mono opacity-75">{conf}</span>}
              </motion.button>
            )
          })}
        </div>
      )}
    </div>
  )
}
