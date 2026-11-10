import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Keyboard, Lightbulb, Loader2, Mic, RefreshCw, SlidersHorizontal, Sparkles, Square, Wand2, Wrench, X } from 'lucide-react'
import { toast } from 'sonner'
import { api, ApiError, errMessage } from '../../lib/api'
import { BRIEF_COMMANDS } from '../../lib/ir'
import { cn, ms, reduceMotion } from '../../lib/utils'
import { OpChip } from '../../components/common'
import { Button, IconButton, Kbd, Menu, MenuItem, MenuLabel, MenuSwitch, Textarea } from '../../components/ui'
import { StepCard } from './parts'
import { useStudio } from './Studio'

const MAX_SEC = 60

function pickMime() {
  const c = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  return c.find((m) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported?.(m)) || ''
}

/** Mic recorder with a live level orb + scrolling waveform (Web Audio AnalyserNode). */
function useRecorder() {
  const [state, setState] = useState('idle') // idle | recording | stopping
  const [secs, setSecs] = useState(0)
  const [level, setLevel] = useState(0)
  const hist = useRef(new Array(56).fill(0))
  const r = useRef({})

  const cleanup = () => {
    const x = r.current
    cancelAnimationFrame(x.raf)
    clearInterval(x.timer)
    x.stream?.getTracks().forEach((t) => t.stop())
    x.ctx?.close().catch(() => {})
    r.current = {}
    setLevel(0)
  }
  useEffect(() => cleanup, [])

  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') throw new Error('This browser cannot record audio. Type the instruction instead.')
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    const mime = pickMime()
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    const chunks = []
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const src = ctx.createMediaStreamSource(stream)
    const an = ctx.createAnalyser()
    an.fftSize = 1024
    src.connect(an)
    const buf = new Float32Array(an.fftSize)
    let last = 0
    const tick = (t) => {
      an.getFloatTimeDomainData(buf)
      let sum = 0
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
      const rms = Math.sqrt(sum / buf.length)
      const v = Math.min(1, rms * 5.5)
      if (t - last > 50) {
        last = t
        hist.current = [...hist.current.slice(1), v]
        setLevel(v)
      }
      r.current.raf = requestAnimationFrame(tick)
    }
    r.current = { stream, rec, chunks, ctx, t0: Date.now(), raf: requestAnimationFrame(tick) }
    r.current.timer = setInterval(() => {
      const s = (Date.now() - r.current.t0) / 1000
      setSecs(s)
      if (s >= MAX_SEC) stopRef.current?.()
    }, 200)
    hist.current = new Array(56).fill(0)
    setSecs(0)
    rec.start(250)
    setState('recording')
  }
  const stop = () =>
    new Promise((res) => {
      const x = r.current
      if (!x.rec) return res(null)
      setState('stopping')
      x.rec.onstop = () => {
        const blob = new Blob(x.chunks, { type: x.rec.mimeType || 'audio/webm' })
        cleanup()
        setState('idle')
        res(blob)
      }
      x.rec.stop()
    })
  const stopRef = useRef(null)
  stopRef.current = stop
  const cancel = () => {
    const x = r.current
    if (x.rec && x.rec.state !== 'inactive') {
      x.rec.onstop = null
      x.rec.stop()
    }
    cleanup()
    setState('idle')
  }
  return { state, secs, level, hist: hist.current, start, stop, cancel }
}

function Orb({ level, recording, busy, onClick, disabled }) {
  const calm = reduceMotion()
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={recording ? 'Stop recording' : 'Start recording'} className="relative grid size-14 shrink-0 place-items-center rounded-full disabled:opacity-50">
      {recording && !calm && (
        <>
          <motion.span className="absolute inset-0 rounded-full bg-accent/15" animate={{ scale: 1 + level * 0.32 }} transition={{ type: 'spring', stiffness: 300, damping: 18 }} />
          <motion.span className="absolute inset-1.5 rounded-full bg-accent/20" animate={{ scale: 1 + level * 0.2 }} transition={{ type: 'spring', stiffness: 400, damping: 20 }} />
        </>
      )}
      <motion.span whileTap={{ scale: 0.92 }} className={cn('relative grid size-12 place-items-center rounded-full shadow-[inset_0_1px_0_rgb(255_255_255/0.2),0_6px_18px_-6px_var(--accent)] transition-colors', recording ? 'bg-fg text-bg' : 'bg-accent text-accent-fg hover:bg-accent-hover')}>
        {busy ? <Loader2 className="size-5 animate-spin" /> : recording ? <Square className="size-4 fill-current" /> : <Mic className="size-5" strokeWidth={2} />}
      </motion.span>
    </button>
  )
}

function Wave({ hist, active }) {
  return (
    <div className="mt-1 flex h-8 flex-1 items-center gap-[2px] overflow-hidden" aria-hidden>
      {hist.map((v, i) => (
        <span key={i} className={cn('w-[3px] shrink-0 rounded-full transition-[height] duration-75', active ? 'bg-accent' : 'bg-line-strong')} style={{ height: `${Math.max(8, Math.min(100, v * 100 + 6))}%`, opacity: active ? 0.35 + (i / hist.length) * 0.65 : 0.6 }} />
      ))}
    </div>
  )
}

export default function VoicePanel() {
  const s = useStudio()
  const rec = useRecorder()
  const [text, setText] = useState(() => s.sampleSay || '')
  useEffect(() => {
    const h = (e) => {
      setText(e.detail || '')
      setSource('text')
    }
    addEventListener('ngui:say', h)
    return () => removeEventListener('ngui:say', h)
  }, [])
  const [source, setSource] = useState('text')
  const [transcribing, setTranscribing] = useState(false)
  const [tMs, setTMs] = useState(null)
  const [fresh, setFresh] = useState(false)
  const [interp, setInterp] = useState(null)
  const [interpBusy, setInterpBusy] = useState(false)
  const busy = s.run?.active
  const first = !s.current

  const toggleMic = async () => {
    if (rec.state === 'recording') {
      const blob = await rec.stop()
      if (!blob || blob.size < 1200) return toast.error('That recording was too short', { description: 'Hold for a second or two and speak clearly.' })
      setTranscribing(true)
      const t0 = performance.now()
      try {
        const r = await api.voiceToText(blob)
        const took = Math.round(performance.now() - t0)
        setText(r.text || '')
        setSource('voice')
        setTMs(r.duration_ms ?? took)
        setInterp(null)
        if (!r.text?.trim()) toast('No speech detected', { description: 'Try again a little closer to the mic.' })
      } catch (e) {
        if (e instanceof ApiError && e.noKey) s.setKeyError(true)
        toast.error('Transcription failed', { description: errMessage(e) })
      } finally {
        setTranscribing(false)
      }
      return
    }
    try {
      await rec.start()
    } catch (e) {
      toast.error(e.name === 'NotAllowedError' ? 'Microphone permission denied' : 'Could not start the microphone', { description: e.name === 'NotAllowedError' ? 'Allow mic access in the browser, or type the instruction.' : e.message })
    }
  }

  const submit = async () => {
    const t = text.trim()
    if (!t || busy) return
    s.setMobileTab('preview')
    const v = await s.send({ text: t, source, transcribeMs: source === 'voice' ? tMs : null, fresh: fresh && !first })
    if (v) {
      setText('')
      setSource('text')
      setTMs(null)
      setFresh(false)
      setInterp(null)
    }
  }
  const dryRun = async () => {
    const t = text.trim()
    if (!t) return
    setInterpBusy(true)
    try {
      setInterp(await api.interpret(t, s.current ? s.id : undefined))
    } catch (e) {
      if (e instanceof ApiError && e.noKey) s.setKeyError(true)
      toast.error('Could not interpret the instruction', { description: errMessage(e) })
    } finally {
      setInterpBusy(false)
    }
  }

  const open = s.openStep === 'describe'
  const recent = (s.versions || []).filter((v) => v.text).slice(0, 2)
  const recording = rec.state === 'recording'
  const mm = `${Math.floor(rec.secs / 60)}:${String(Math.floor(rec.secs % 60)).padStart(2, '0')}`

  return (
    <StepCard id="step-describe" n={2} title={first ? 'Describe it' : 'Refine it'} open={open} onToggle={() => s.setOpenStep(open ? null : 'describe')} aside={first ? <span>New UI</span> : <span>Edits v{s.current.number}</span>} summary={<p className="line-clamp-2 text-[13px] text-muted">{s.current?.text ? `Last: “${s.current.text}”` : 'Say or type what the screen is and how it behaves.'}</p>}>

      <div className="flex items-center gap-3 rounded-xl border border-line bg-surface-2/60 p-2 pr-4">
        <Orb level={rec.level} recording={recording} busy={transcribing || rec.state === 'stopping'} onClick={toggleMic} disabled={transcribing || busy} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between text-[13px]">
            <span className={cn(recording ? 'font-medium text-accent' : 'text-muted')}>{recording ? 'Listening…' : transcribing ? 'Transcribing…' : 'Tap the mic and speak'}</span>
            <span className="font-mono text-[12px] text-subtle tnum">{recording ? mm : tMs != null && source === 'voice' ? ms(tMs) : ''}</span>
          </div>
          <Wave hist={rec.hist} active={recording} />
        </div>
        {recording && <button onClick={rec.cancel} aria-label="Discard recording" className="grid size-8 place-items-center rounded-lg text-subtle hover:bg-surface-hover hover:text-fg"><X className="size-4" /></button>}
      </div>

      <div className="mt-4">
        <Textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            if (!e.target.value) setSource('text')
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
              e.preventDefault()
              submit()
            }
          }}
          rows={3}
          placeholder={first ? 'Say what the screen is and how it behaves, e.g. a login page with email and password fields, a login button, and an error on empty submit' : 'What should change? e.g. Make the login button blue'}
          aria-label="Instruction"
        />
        <div className="mt-2 flex items-center justify-between text-[12px] text-subtle">
          <span className="flex items-center gap-1.5">{source === 'voice' ? <><Mic className="size-3.5 text-accent" />From voice, editable</> : <><Keyboard className="size-3.5" />Typed</>}</span>
          <span className="hidden items-center gap-1 sm:flex"><Kbd>Ctrl</Kbd><Kbd>↵</Kbd> to send</span>
        </div>

        <AnimatePresence>
          {interp && (
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-4 rounded-xl border border-dashed border-line-strong p-3">
              <div className="mb-2 flex items-center justify-between text-[13px] text-muted"><span>Understood as {interp.ops?.length || 0} op{interp.ops?.length === 1 ? '' : 's'} (dry run, not saved)</span><span className="font-mono text-[12px]">{ms(interp.latency_ms)}</span></div>
              <div className="flex flex-col items-start gap-2">{(interp.ops || []).map((o, i) => <OpChip key={i} op={o} />)}</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {recent.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-[13px] text-muted">Recent instructions</div>
          <ul className="space-y-2">
            {recent.map((v) => (
              <li key={v.number}>
                <button onClick={() => { setText(v.text); setSource('text'); setInterp(null) }} className="flex w-full items-start gap-3 rounded-xl border border-line px-3 py-2.5 text-left text-[13px] transition-colors hover:border-line-strong hover:bg-surface-hover/50">
                  <span className="mt-px shrink-0 font-mono text-[12px] text-subtle">v{v.number}</span>
                  <span className="min-w-0 flex-1 truncate">{v.text}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex items-center gap-2 border-t border-line pt-4">
        <Menu side="top" align="left" width={320} trigger={({ open, toggle }) => <Button size="sm" variant="ghost" icon={Lightbulb} onClick={toggle} className={cn(open && 'bg-surface-hover text-fg')}>Examples</Button>}>
          {(close) => (
            <>
              <MenuLabel>Try an instruction</MenuLabel>
              {BRIEF_COMMANDS.map((c, i) => (
                <button key={c} onClick={() => { setText(c); setSource('text'); setInterp(null); close() }} className={cn('block w-full rounded-lg px-2 py-2 text-left text-[13px] leading-snug hover:bg-surface-hover', i === 0 && !first && 'opacity-60')}>{c}</button>
              ))}
            </>
          )}
        </Menu>
        <Menu side="top" align="left" width={280} trigger={({ open, toggle }) => <IconButton icon={SlidersHorizontal} label="Options" active={open} onClick={toggle} />}>
          {(close) => (
            <>
              <MenuLabel>Options</MenuLabel>
              <MenuSwitch icon={Wrench} checked={s.autoRepair} onChange={s.setAutoRepair}>Auto repair</MenuSwitch>
              {!first && <MenuSwitch icon={RefreshCw} checked={fresh} onChange={setFresh}>Fresh from sketch</MenuSwitch>}
              <div className="my-1.5 h-px bg-line" />
              <MenuItem icon={Sparkles} disabled={!text.trim() || interpBusy} onClick={() => { close(); dryRun() }}>{interpBusy ? 'Interpreting…' : 'Interpret (dry run)'}</MenuItem>
            </>
          )}
        </Menu>
        <div className="ml-auto">
          {busy ? (
            <Button variant="secondary" onClick={s.cancel}>Cancel</Button>
          ) : (
            <Button icon={Wand2} disabled={!text.trim() || recording || transcribing} onClick={submit}>{first || fresh ? 'Generate UI' : 'Apply change'}</Button>
          )}
        </div>
      </div>
    </StepCard>
  )
}
