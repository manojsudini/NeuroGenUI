import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { Check, ChevronRight, Eye, PenLine, Workflow } from 'lucide-react'
import { toast } from 'sonner'
import { api, ApiError, errMessage } from '../../lib/api'
import { useMedia } from '../../lib/store'
import { STAGES } from '../../lib/ir'
import { cn } from '../../lib/utils'
import { CommandPalette, HealthPill, Logo, ThemeToggle, openCmdK } from '../../components/common'
import { Badge, Banner, Button, ErrorState, IconButton, Kbd, Segmented, Skeleton, Tabs } from '../../components/ui'
import { Search } from 'lucide-react'
import SketchPanel from './SketchPanel'
import VoicePanel from './VoicePanel'
import PipelineTrace from './PipelineTrace'
import Preview from './Preview'
import IrTab from './IrTab'
import CodeTab from './CodeTab'
import ValidationTab from './ValidationTab'
import VersionsTab from './VersionsTab'

const Ctx = createContext(null)
export const useStudio = () => useContext(Ctx)

const emptyStages = () => Object.fromEntries(STAGES.map((s) => [s.id, { status: 'idle', ms: null }]))

export default function Studio() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const sampleUrl = params.get('sample')
  const sampleSay = params.get('say')
  const wide = useMedia('(min-width: 1024px)')
  const xl = useMedia('(min-width: 1280px)')

  /* ---------- project + versions ---------- */
  const [project, setProject] = useState(null)
  const [loadErr, setLoadErr] = useState(null)
  const [versions, setVersions] = useState([])
  const [current, setCurrent] = useState(null) // full Version
  const [loadingVersion, setLoadingVersion] = useState(false)

  const refreshVersions = useCallback(async () => {
    try {
      const v = await api.versions(id)
      setVersions(Array.isArray(v) ? [...v].sort((a, b) => b.number - a.number) : [])
    } catch {
      /* list stays as is */
    }
  }, [id])

  const load = useCallback(async () => {
    setLoadErr(null)
    try {
      const p = await api.project(id)
      setProject(p)
      const latest = p.latest && typeof p.latest === 'object' ? p.latest : p.version && typeof p.version === 'object' ? p.version : p.latest_version_full || null
      const list = Array.isArray(p.versions_list) ? p.versions_list : Array.isArray(p.versions) ? p.versions : null
      if (list) setVersions([...list].sort((a, b) => b.number - a.number))
      else refreshVersions()
      if (latest) setCurrent(latest)
      else if (typeof p.latest_version === 'number' && p.latest_version > 0) setCurrent(await api.version(id, p.latest_version))
      else setCurrent(null)
    } catch (e) {
      setLoadErr(e)
    }
  }, [id, refreshVersions])
  useEffect(() => {
    load()
  }, [load])

  const selectVersion = useCallback(
    async (n) => {
      if (current?.number === n) return
      setLoadingVersion(true)
      try {
        setCurrent(await api.version(id, n))
      } catch (e) {
        toast.error(`Could not load version ${n}`, { description: errMessage(e) })
      } finally {
        setLoadingVersion(false)
      }
    },
    [id, current],
  )
  /** A new Version came back from any endpoint: show it and refresh the timeline. */
  const adopt = useCallback(
    (v, note) => {
      if (!v || typeof v !== 'object' || v.number == null) return
      setCurrent(v)
      setVersions((list) => [v, ...list.filter((x) => x.number !== v.number)].sort((a, b) => b.number - a.number))
      refreshVersions()
      if (v.analysis) setAnalysis(v.analysis)
      if (note) toast.success(note, { description: `Version ${v.number} saved` })
    },
    [refreshVersions],
  )

  /* ---------- sketch + analysis ---------- */
  const sketchRef = useRef(null) // DrawCanvas imperative api
  const [sketch, setSketch] = useState({ id: null, url: null, dirty: false })
  const [analysis, setAnalysis] = useState(null)
  const [mode, setMode] = useState('hybrid')
  useEffect(() => {
    if (current?.analysis) setAnalysis(current.analysis)
    if (current?.sketch_id && !sketch.dirty) setSketch((s) => ({ ...s, id: current.sketch_id }))
  }, [current?.number]) // eslint-disable-line react-hooks/exhaustive-deps

  const uploadSketch = useCallback(async () => {
    const blob = await sketchRef.current?.getBlob()
    if (!blob) throw new Error('The canvas is empty. Draw or upload a sketch first.')
    const r = await api.uploadSketch(blob, id)
    setSketch({ id: r.sketch_id, url: r.url, dirty: false })
    return r
  }, [id])

  /* ---------- pipeline run (generate / modify, streamed) ---------- */
  const [run, setRun] = useState(null) // {active, text, source, stages, ops, error, kind, startedAt, total}
  const [autoRepair, setAutoRepair] = useState(true)
  const [keyError, setKeyError] = useState(false)
  const abortRef = useRef(null)

  const send = useCallback(
    async ({ text, source = 'text', transcribeMs = null, fresh = false }) => {
      const first = !current || fresh
      const stages = emptyStages()
      if (transcribeMs != null) stages.transcribe = { status: 'done', ms: transcribeMs, local: true }
      const t0 = performance.now()
      setRun({ active: true, text, source, stages, ops: [], error: null, kind: first ? 'generate' : 'modify', startedAt: Date.now() })
      // stages measured in the browser (upload, transcribe) keep their client timing
      const setStage = (stage, patch, force) => setRun((r) => (r && r.stages[stage] && (force || !r.stages[stage].local) ? { ...r, stages: { ...r.stages, [stage]: { ...r.stages[stage], ...patch } } } : r))
      const ctrl = new AbortController()
      abortRef.current = ctrl
      try {
        let sketchId = sketch.dirty ? null : sketch.id
        const hasInk = sketchRef.current && !sketchRef.current.isEmpty()
        if (first && hasInk && !sketchId) {
          setStage('upload', { status: 'start', local: true }, true)
          const u0 = performance.now()
          const r = await uploadSketch()
          sketchId = r.sketch_id
          setStage('upload', { status: 'done', ms: Math.round(performance.now() - u0), local: true }, true)
        }
        const onEvent = (ev) => {
          if (ev.event === 'stage' && ev.stage) {
            setStage(ev.stage, { status: ev.status === 'start' ? 'start' : ev.status === 'error' ? 'error' : ev.status === 'skip' || ev.status === 'skipped' ? 'skipped' : 'done', ms: ev.ms ?? null, data: ev.data })
            if (Array.isArray(ev.data?.ops)) setRun((r) => ({ ...r, ops: ev.data.ops }))
            if (ev.stage === 'analyze_sketch' && Array.isArray(ev.data?.components)) setAnalysis((a) => ({ ...(a || {}), ...ev.data }))
          }
        }
        const v = first
          ? await api.generate({ project_id: id, sketch_id: sketchId || undefined, text, source, mode, auto_repair: autoRepair }, onEvent, ctrl.signal)
          : await api.modify({ project_id: id, text, source, base_version: current.number, auto_repair: autoRepair }, onEvent, ctrl.signal)
        setKeyError(false)
        setRun((r) => {
          const st = { ...r.stages }
          for (const s of STAGES) {
            const t = v?.timings?.[s.id]
            const cur = st[s.id]
            if (cur.local) continue
            // a stage that never reported over the stream and took 0 ms did not run
            if (cur.status === 'idle') st[s.id] = t ? { ...cur, status: 'done', ms: t } : { ...cur, status: 'skipped' }
            else if (cur.status === 'start') st[s.id] = { ...cur, status: 'done', ms: t ?? cur.ms }
            else if (t != null && cur.status === 'done') st[s.id] = { ...cur, ms: t }
          }
          return { ...r, active: false, stages: st, ops: v?.ops?.length ? v.ops : r.ops, changes: v?.changes || [], total: v?.timings?.total ?? Math.round(performance.now() - t0), version: v?.number, score: v?.validation?.score }
        })
        adopt(v)
        toast.success(first ? 'UI generated' : 'Change applied', { description: `Version ${v.number}${v?.validation?.score != null ? ` · validation ${Math.round(v.validation.score * 100)}%` : ''}` })
        return v
      } catch (e) {
        if (e.name === 'AbortError') {
          setRun((r) => r && { ...r, active: false, error: 'Cancelled' })
          return null
        }
        if (e instanceof ApiError && e.noKey) setKeyError(true)
        setRun((r) => {
          if (!r) return r
          const st = { ...r.stages }
          for (const k in st) if (st[k].status === 'start') st[k] = { ...st[k], status: 'error' }
          return { ...r, active: false, stages: st, error: errMessage(e) }
        })
        toast.error(first ? 'Generation failed' : 'Modification failed', { description: errMessage(e) })
        return null
      } finally {
        abortRef.current = null
      }
    },
    [current, sketch, id, mode, autoRepair, uploadSketch, adopt],
  )
  const cancel = () => abortRef.current?.abort()

  /* ---------- preview bridge (iframe postMessage, contract §5) ---------- */
  const frameRef = useRef(null)
  const [runtime, setRuntime] = useState({ ready: false, errors: [], nodes: [], live: false })
  const post = useCallback((msg) => frameRef.current?.contentWindow?.postMessage(msg, location.origin), [])
  const runCode = useCallback(
    (code) => {
      setRuntime((r) => ({ ...r, errors: [], live: true }))
      post({ type: 'ngui:code', code })
    },
    [post],
  )
  const highlight = useCallback((nodeId) => post({ type: 'ngui:highlight', id: nodeId || null }), [post])
  useEffect(() => {
    const h = (e) => {
      if (e.source !== frameRef.current?.contentWindow) return
      const d = e.data || {}
      if (d.type === 'ngui:ready') setRuntime((r) => ({ ...r, ready: true }))
      if (d.type === 'ngui:error') setRuntime((r) => ({ ...r, errors: [...r.errors.slice(-9), { message: d.message, stack: d.stack, at: Date.now() }] }))
      if (d.type === 'ngui:rendered') setRuntime((r) => ({ ...r, nodes: d.nodes || [] }))
    }
    addEventListener('message', h)
    return () => removeEventListener('message', h)
  }, [])

  /* ---------- selection ---------- */
  const [selectedId, setSelectedId] = useState(null)
  const [tab, setTab] = useState('ir')
  const [mobileTab, setMobileTab] = useState('sketch')
  const [openStep, setOpenStep] = useState('sketch') // left zone accordion: 'sketch' | 'describe' | null
  const autoOpened = useRef(false)
  useEffect(() => {
    // a project that already has a version opens on Describe (refine); a fresh one on Sketch
    if (autoOpened.current || !project) return
    autoOpened.current = true
    if (current && !sampleUrl) setOpenStep('describe')
  }, [project, current, sampleUrl])

  /* ---------- step flow: 1 Sketch, 2 Describe, 3 Result ---------- */
  const sketchDone = !!(analysis || sketch.id || project?.sketch_url || sketch.dirty)
  const stepState = [sketchDone, !!current, !!current && !run?.active]
  const step = run?.active ? 3 : stepState.findIndex((x) => !x) === -1 ? 3 : stepState.findIndex((x) => !x) + 1
  const goStep = useCallback(
    (n) => {
      if (n === 3) return setMobileTab('preview')
      setOpenStep(n === 1 ? 'sketch' : 'describe')
      setMobileTab('sketch')
      setTimeout(() => document.getElementById(n === 1 ? 'step-sketch' : 'step-describe')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 80)
    },
    [],
  )

  const value = useMemo(
    () => ({
      id, project, versions, current, selectVersion, loadingVersion, adopt, reload: load, refreshVersions,
      sketchRef, sketch, setSketch, uploadSketch, analysis, setAnalysis, mode, setMode, sampleUrl, sampleSay, clearSample: () => setParams({}, { replace: true }),
      run, send, cancel, autoRepair, setAutoRepair, keyError, setKeyError,
      frameRef, runtime, setRuntime, runCode, highlight,
      selectedId, setSelectedId, tab, setTab, setMobileTab, step, stepState, goStep, openStep, setOpenStep,
    }),
    [id, project, versions, current, selectVersion, loadingVersion, adopt, load, refreshVersions, sketch, uploadSketch, analysis, mode, sampleUrl, setParams, run, send, autoRepair, keyError, runtime, runCode, highlight, selectedId, tab, step, goStep, openStep],
  )

  if (loadErr) {
    return (
      <div className="min-h-dvh">
        <StudioBar />
        <div className="mx-auto max-w-lg pt-16"><ErrorState error={loadErr} onRetry={load} /><div className="text-center"><Link to="/" className="text-[13px] font-medium text-accent">Back to projects</Link></div></div>
      </div>
    )
  }

  const left = (
    <div className="space-y-6">
      <SketchPanel />
      <VoicePanel />
    </div>
  )
  const result = (parts) => <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-xs">{parts}</section>

  return (
    <Ctx.Provider value={value}>
      <div className="min-h-dvh bg-bg">
        <StudioBar />
        {keyError && (
          <div className="border-b border-line px-4 py-3 sm:px-6">
            <Banner tone="warning" onClose={() => setKeyError(false)}>
              <b>OpenAI key not configured on the server.</b> Generation, voice transcription and vision labelling need <code className="font-mono text-[12px]">OPENAI_API_KEY</code> in <code className="font-mono text-[12px]">project/.env</code>. Restart the backend after adding it. Sketch analysis in <b>cv</b> mode still works.
            </Banner>
          </div>
        )}
        {wide ? (
          <div className={cn('grid items-start gap-6 px-6 py-6', xl ? 'grid-cols-[minmax(360px,420px)_minmax(0,1fr)]' : 'grid-cols-[340px_minmax(0,1fr)]')}>
            <div>{left}</div>
            <div className="sticky top-[80px] h-[calc(100dvh-104px)] min-h-[520px]">
              {result(
                <>
                  <PipelineTrace />
                  {xl ? (
                    <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(340px,400px)] 2xl:grid-cols-[minmax(0,1fr)_440px]">
                      <div className="flex min-h-0 min-w-0 flex-col border-r border-line"><Preview /></div>
                      <div className="min-h-0 min-w-0"><Inspector /></div>
                    </div>
                  ) : (
                    <>
                      <div className="flex h-14 shrink-0 items-center border-b border-line px-4">
                        <Segmented value={mobileTab === 'inspect' ? 'inspect' : 'preview'} onChange={setMobileTab} options={[{ value: 'preview', label: 'Preview', icon: Eye }, { value: 'inspect', label: 'Inspect', icon: Workflow }]} />
                      </div>
                      <div className={cn('flex min-h-0 flex-1 flex-col', mobileTab === 'inspect' && 'hidden')}><Preview /></div>
                      <div className={cn('min-h-0 flex-1', mobileTab !== 'inspect' && 'hidden')}><Inspector /></div>
                    </>
                  )}
                </>,
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="p-4 pb-28">
              <div className={cn(mobileTab !== 'sketch' && 'hidden')}>{left}</div>
              <div className={cn('h-[calc(100dvh-168px)] min-h-[480px]', mobileTab !== 'preview' && 'hidden')}>{result(<><PipelineTrace /><div className="flex min-h-0 flex-1 flex-col"><Preview /></div></>)}</div>
              <div className={cn('h-[calc(100dvh-168px)] min-h-[480px]', mobileTab !== 'inspect' && 'hidden')}>{result(<Inspector />)}</div>
            </div>
            <MobileStudioBar tab={mobileTab} setTab={setMobileTab} running={run?.active} />
          </>
        )}
      </div>
      <CommandPalette />
    </Ctx.Provider>
  )
}

const STEPS = [
  { n: 1, label: 'Sketch' },
  { n: 2, label: 'Describe' },
  { n: 3, label: 'Result' },
]
function StepIndicator() {
  const s = useStudio()
  if (!s) return null
  return (
    <ol className="mx-auto hidden items-center lg:flex" aria-label="Progress">
      {STEPS.map((x, i) => {
        const done = s.stepState[i] && !(x.n === 3 && s.run?.active)
        const active = s.step === x.n
        return (
          <li key={x.n} className="flex items-center">
            {i > 0 && <span className={cn('mx-3 h-px w-10 transition-colors', s.stepState[i - 1] ? 'bg-accent/50' : 'bg-line-strong')} />}
            <button type="button" onClick={() => s.goStep(x.n)} aria-current={active ? 'step' : undefined} className={cn('flex h-9 items-center gap-2 rounded-full pr-3 pl-1.5 text-[13px] transition-colors', active ? 'bg-accent-soft text-accent-soft-fg' : 'text-muted hover:bg-surface-hover hover:text-fg')}>
              <span className={cn('grid size-6 place-items-center rounded-full border text-[12px] tnum transition-colors', done ? 'border-accent bg-accent text-accent-fg' : active ? 'border-accent text-accent' : 'border-line-strong text-subtle', active && s.run?.active && 'ping-soft')}>
                {done ? <Check className="size-3.5" strokeWidth={3} /> : x.n}
              </span>
              <span className="font-medium">{x.label}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

function StudioBar() {
  const s = useStudio()
  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-line bg-bg/90 px-4 backdrop-blur-xl sm:px-6">
      <Logo compact />
      <nav className="flex min-w-0 items-center gap-2 text-[14px] lg:w-[300px] lg:shrink-0 xl:w-[360px]">
        <Link to="/" className="hidden text-muted hover:text-fg sm:inline">Projects</Link>
        <ChevronRight className="hidden size-4 text-subtle sm:block" />
        {s?.project ? <span className="truncate font-medium">{s.project.name}</span> : <Skeleton className="h-4 w-32" />}
        {s?.current && (
          <Badge className="ml-1 hidden shrink-0 font-mono sm:inline-flex">v{s.current.number}{s.versions[0] && s.current.number !== s.versions[0].number ? ` of ${s.versions[0].number}` : ''}</Badge>
        )}
      </nav>
      <StepIndicator />
      <div className="ml-auto flex items-center gap-2 lg:ml-0 lg:w-[300px] lg:shrink-0 lg:justify-end xl:w-[360px]">
        <button onClick={openCmdK} className="hidden h-9 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-[13px] text-subtle shadow-xs transition hover:border-line-strong xl:flex">
          <Search className="size-4" />Jump to<span className="ml-3 flex gap-0.5"><Kbd>Ctrl</Kbd><Kbd>K</Kbd></span>
        </button>
        <div className="xl:hidden"><IconButton icon={Search} label="Search (Ctrl+K)" onClick={openCmdK} /></div>
        <HealthPill className="hidden sm:block" />
        <ThemeToggle />
      </div>
    </header>
  )
}

function MobileStudioBar({ tab, setTab, running }) {
  const items = [
    { v: 'sketch', l: 'Create', i: PenLine },
    { v: 'preview', l: 'Result', i: Eye },
    { v: 'inspect', l: 'Inspect', i: Workflow },
  ]
  return (
    <nav className="pb-safe fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-line bg-bg">
      {items.map((t) => (
        <button key={t.v} onClick={() => setTab(t.v)} className={cn('relative flex flex-col items-center gap-1 py-3 text-[12px] font-medium', tab === t.v ? 'text-accent' : 'text-muted')}>
          {tab === t.v && <motion.span layoutId="studio-mtab" className="absolute inset-x-6 top-0 h-0.5 rounded-full bg-accent" />}
          <t.i className="size-5" strokeWidth={1.8} />
          {t.l}
          {t.v === 'preview' && running && <span className="ping-soft absolute top-2.5 right-[calc(50%-18px)] size-2 rounded-full bg-accent" />}
        </button>
      ))}
    </nav>
  )
}

function Inspector() {
  const s = useStudio()
  const opts = [
    { value: 'ir', label: 'IR tree' },
    { value: 'code', label: 'Code' },
    { value: 'validation', label: 'Validation' },
    { value: 'versions', label: 'Versions', count: s.versions.length || undefined },
  ]
  return (
    <div className="flex h-full min-h-0 flex-col">
      <Tabs value={s.tab} onChange={s.setTab} options={opts} className="shrink-0 px-2" />
      <div className="relative min-h-0 flex-1">
        {s.loadingVersion && <div className="absolute inset-x-0 top-0 z-10 h-0.5 overflow-hidden"><div className="shimmer h-full w-full !bg-accent/40" /></div>}
        {!s.project ? (
          <div className="space-y-3 p-4">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-9" style={{ width: `${90 - i * 12}%` }} />)}</div>
        ) : s.tab === 'ir' ? (
          <IrTab />
        ) : s.tab === 'code' ? (
          <CodeTab />
        ) : s.tab === 'validation' ? (
          <ValidationTab />
        ) : (
          <VersionsTab />
        )}
      </div>
    </div>
  )
}

/** Empty state shared by inspector tabs before anything has been generated: shows real progress, not blank space. */
export function NotGenerated({ what }) {
  const s = useStudio()
  const sk = s.sketch.url || s.project?.sketch_url
  const n = s.analysis?.components?.length || 0
  const rows = [
    { done: !!sk, title: 'Sketch', text: sk ? (n ? `${n} components detected` : 'On the canvas, not analysed yet') : 'Nothing drawn yet' },
    { done: !!s.analysis, title: 'Detection', text: s.analysis ? `${n} components, ${s.analysis.mode || s.mode} mode` : 'Optional: run Analyze on the sketch' },
    { done: false, title: 'Instruction', text: 'Say or type what the screen should do' },
  ]
  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="rounded-xl border border-line bg-surface-2/50 p-4">
        <div className="flex items-start gap-4">
          <div className="grid h-24 w-20 shrink-0 place-items-center overflow-hidden rounded-lg border border-line bg-white">
            {sk ? <img src={sk} alt="Your sketch" className="size-full object-contain p-1" /> : <img src="/img/wireframes-paper.jpg" alt="" className="size-full object-cover opacity-80" />}
          </div>
          <div className="min-w-0">
            <h3 className="text-[15px] font-semibold">Nothing generated yet</h3>
            <p className="mt-1 text-[13px] text-muted">{what} appears here after the first instruction.</p>
          </div>
        </div>
        <ul className="mt-4 space-y-3">
          {rows.map((r) => (
            <li key={r.title} className="flex items-center gap-3 text-[13px]">
              <span className={cn('grid size-6 shrink-0 place-items-center rounded-full border', r.done ? 'border-accent bg-accent text-accent-fg' : 'border-line-strong text-subtle')}>{r.done ? <Check className="size-3.5" strokeWidth={3} /> : <span className="size-1.5 rounded-full bg-current" />}</span>
              <span className="font-medium">{r.title}</span>
              <span className="min-w-0 truncate text-muted">{r.text}</span>
            </li>
          ))}
        </ul>
      </div>
      <Button size="sm" className="mt-4 w-full" onClick={() => s.goStep(2)}>Describe the screen</Button>
      <div className="mt-6">
        <div className="mb-3 text-[13px] text-muted">What you get after generating</div>
        <ul className="space-y-2">
          {[['IR tree', 'every component, editable and diffable'], ['Code', 'real React files you can edit and export'], ['Validation', 'Playwright layout and behaviour checks'], ['Versions', 'every instruction kept, with compare and restore']].map(([t, d]) => (
            <li key={t} className="flex items-baseline gap-3 rounded-lg border border-line px-3 py-2.5 text-[13px]"><span className="w-20 shrink-0 font-medium">{t}</span><span className="text-muted">{d}</span></li>
          ))}
        </ul>
      </div>
    </div>
  )
}
