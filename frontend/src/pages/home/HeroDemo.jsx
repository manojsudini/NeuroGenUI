import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Check, Mic } from 'lucide-react'
import { cn, reduceMotion } from '../../lib/utils'

const CMD = 'make the login button blue'
const EASE = [0.16, 1, 0.3, 1]
// stage: 0 blank paper, 1 sketch draws, 2 boxes detected, 3 voice, 4 rendered, 5 button blue + verified
const SEQ = [[0, 0], [600, 1], [3600, 2], [6000, 3], [8800, 4], [10600, 5], [15200, 0]]
const LOOP_MS = 16000
const STEPS = ['Sketch', 'Detect', 'Voice', 'Compile', 'Verify']

// hand-drawn strokes on a 400x300 board
const STROKES = [
  'M101 28 C150 25 250 30 299 27 C302 80 297 200 300 272 C250 275 150 270 100 273 C98 200 103 80 101 28',
  'M151 64 q7 -9 14 0 t14 0 t14 0 t14 0 t14 0 t14 0 t14 0',
  'M122 96 l24 1',
  'M121 103 L279 101 L281 127 L120 128 L121 103',
  'M122 140 l32 -1',
  'M121 147 L279 149 L280 173 L120 172 L121 147',
  'M121 198 L279 196 L281 231 L119 232 L121 198',
  'M181 214 q6 -8 11 0 t11 0 t11 0 t11 0',
]
const BOXES = [
  { l: 'heading', b: [148, 50, 104, 28] },
  { l: 'input', b: [116, 90, 168, 40] },
  { l: 'input', b: [116, 134, 168, 42] },
  { l: 'button', b: [116, 194, 168, 42] },
]
const px = (x, y, w, h) => ({ left: `${(x / 400) * 100}%`, top: `${(y / 300) * 100}%`, ...(w != null && { width: `${(w / 400) * 100}%`, height: `${(h / 300) * 100}%` }) })
const fs = (cqw, min = 10) => ({ fontSize: `max(${min}px, ${cqw}cqw)` })

function Wave({ live }) {
  return (
    <span className="flex h-6 items-center gap-[3px]" aria-hidden>
      {Array.from({ length: 16 }, (_, i) => (
        <motion.span key={i} className="w-[3px] rounded-full bg-accent" style={{ height: 22, originY: 0.5 }} initial={false}
          animate={live ? { scaleY: [0.2, 0.35 + ((i * 37) % 10) / 14, 0.25, 0.9 - ((i * 13) % 5) / 9, 0.2] } : { scaleY: 0.14 }}
          transition={live ? { duration: 0.9 + (i % 4) * 0.12, repeat: Infinity, ease: 'easeInOut', delay: (i % 5) * 0.06 } : { duration: 0.4 }} />
      ))}
    </span>
  )
}

export default function HeroDemo() {
  const [rm] = useState(() => reduceMotion())
  const [stage, setStage] = useState(rm ? 5 : 0)
  const [typed, setTyped] = useState(rm ? CMD : '')

  useEffect(() => {
    if (rm) return undefined
    const timers = []
    const run = () => {
      SEQ.forEach(([t, s]) => timers.push(setTimeout(() => setStage(s), t)))
      timers.push(setTimeout(run, LOOP_MS))
    }
    run()
    return () => timers.forEach(clearTimeout)
  }, [rm])

  useEffect(() => {
    if (rm) return undefined
    if (stage < 3) { setTyped(''); return undefined }
    if (stage > 3) { setTyped(CMD); return undefined }
    let i = 0
    const id = setInterval(() => { i += 1; setTyped(CMD.slice(0, i)); if (i >= CMD.length) clearInterval(id) }, 62)
    return () => clearInterval(id)
  }, [stage, rm])

  const drawn = stage >= 1
  const rendered = stage >= 4
  const blue = stage >= 5
  const step = Math.max(0, Math.min(4, stage - 1 + (stage === 0 ? 1 : 0)))
  const listening = stage === 3

  return (
    <div className="min-w-0 overflow-hidden rounded-3xl border border-line bg-surface shadow-pop" role="img" aria-label="Animation: a hand-drawn login sketch is detected, a voice command makes the button blue, and it becomes a rendered login card">
      <div className="flex h-12 items-center justify-between gap-3 border-b border-line px-4">
        <div className="flex items-center gap-1.5" aria-hidden>
          {STEPS.map((s, i) => (
            <span key={s} className={cn('inline-flex h-6 items-center rounded-full px-2.5 text-[12px] font-medium transition-colors duration-500', i === step ? 'bg-accent text-accent-fg' : i < step ? 'bg-accent-soft text-accent-soft-fg' : 'text-subtle')}>{s}</span>
          ))}
        </div>
        <span className="hidden font-mono text-[12px] text-subtle sm:block">{rendered ? 'login.v2' : 'login.sketch'}</span>
      </div>

      <div className="relative aspect-[4/3] w-full overflow-hidden paper-grid" style={{ containerType: 'inline-size' }}>
        {/* sketch layer */}
        <motion.svg viewBox="0 0 400 300" className="absolute inset-0 size-full" initial={false} animate={{ opacity: rendered ? 0 : 1, filter: rendered ? 'blur(3px)' : 'blur(0px)' }} transition={{ duration: 0.6, ease: EASE }} fill="none" stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {STROKES.map((d, i) => (
            <motion.path key={i} d={d} initial={false} animate={{ pathLength: drawn ? 1 : 0, opacity: drawn ? 1 : 0 }} transition={rm ? { duration: 0 } : drawn ? { duration: i === 0 ? 0.9 : 0.5, delay: i === 0 ? 0 : 0.7 + i * 0.28, ease: 'easeInOut' } : { duration: 0.3 }} />
          ))}
        </motion.svg>

        {/* detected boxes */}
        {BOXES.map((x, i) => {
          const show = stage === 2 || stage === 3
          return (
            <motion.div key={i} className="pointer-events-none absolute" style={px(...x.b)} initial={false} animate={{ opacity: show ? 1 : 0, scale: show ? 1 : 0.94 }} transition={{ duration: 0.45, delay: show && !rm ? i * 0.18 : 0, ease: EASE }}>
              <span className="absolute inset-0 rounded-[3px] border-[1.5px] border-dashed border-accent bg-accent/[0.07]" />
              <span className="absolute top-0 left-[calc(100%+6px)] inline-flex items-center gap-1 rounded-[5px] bg-accent px-1.5 py-0.5 font-mono leading-none text-accent-fg" style={fs(2.5, 10)}>{x.l}</span>
            </motion.div>
          )
        })}

        {/* rendered login card */}
        <motion.div className="absolute rounded-[2.2cqw] border border-[#e4e4e7] bg-white shadow-[0_18px_40px_-18px_rgb(0_0_0/0.35)]" style={px(100, 27, 200, 246)} initial={false} animate={{ opacity: rendered ? 1 : 0, y: rendered ? 0 : 10, scale: rendered ? 1 : 0.985 }} transition={{ duration: 0.6, ease: EASE }} aria-hidden>
          <div className="absolute inset-0 text-[#18181b]">
            <span className="absolute flex items-center justify-center font-semibold tracking-[-0.02em]" style={{ ...px(100, 50, 200, 28), left: 0, ...fs(5.6, 17), width: '100%', top: `${((50 - 27) / 246) * 100}%`, height: `${(28 / 246) * 100}%` }}>Sign in</span>
            {[['Email', 'you@clinic.com', 91, 12], ['Password', '••••••••', 135, 12]].map(([l, v, y]) => (
              <div key={l} className="absolute" style={{ left: `${(16 / 200) * 100}%`, width: `${(168 / 200) * 100}%`, top: `${((y - 27) / 246) * 100}%` }}>
                <div className="text-[#63636e]" style={fs(2.5, 9.5)}>{l}</div>
                <div className="mt-[0.6cqw] flex items-center rounded-[1.2cqw] border border-[#d4d4d8] bg-[#fafafa] px-[2cqw] text-[#71717a]" style={{ height: '6.4cqw', ...fs(2.7, 10) }}>{v}</div>
              </div>
            ))}
            <motion.span className="absolute flex items-center justify-center rounded-[1.4cqw] font-semibold text-white" style={{ left: `${(16 / 200) * 100}%`, width: `${(168 / 200) * 100}%`, top: `${((195 - 27) / 246) * 100}%`, height: `${(38 / 246) * 100}%`, ...fs(3, 11) }} initial={false} animate={{ backgroundColor: blue ? '#2563eb' : '#27272a' }} transition={{ duration: 0.7, ease: EASE }}>Login</motion.span>
          </div>
        </motion.div>

        {/* verified badge */}
        <AnimatePresence>
          {blue && (
            <motion.span key="ok" initial={{ opacity: 0, scale: 0.8, y: 6 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ type: 'spring', stiffness: 420, damping: 26 }} className="absolute right-[3cqw] bottom-[3cqw] inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 font-medium text-success shadow-card" style={fs(2.7, 11)}>
              <Check className="size-3.5" strokeWidth={2.4} />1 change applied, validated
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <div className="flex min-h-16 items-center gap-3 border-t border-line px-4 py-3">
        <span className={cn('grid size-9 shrink-0 place-items-center rounded-full border transition-colors duration-300', listening ? 'border-accent bg-accent text-accent-fg ping-soft' : 'border-line bg-surface-2 text-muted')}><Mic className="size-4" /></span>
        <Wave live={listening && !rm} />
        <div className="min-w-0 flex-1">
          <div className={cn('inline-block max-w-full rounded-2xl rounded-tl-md px-3 py-1.5 text-[14px] transition-colors duration-300', typed ? 'bg-accent-soft text-accent-soft-fg' : 'bg-surface-2 text-subtle')}>
            <span className="block truncate">{typed || 'Say what to change'}{listening && typed.length < CMD.length && <span className="ml-px inline-block h-[1em] w-px translate-y-[2px] animate-pulse bg-current" />}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
