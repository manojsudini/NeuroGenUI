import { Link } from 'react-router-dom'
import { motion } from 'motion/react'
import { ArrowRight, ArrowUpRight, Check, Mic, Minus, Plus, Sparkles } from 'lucide-react'
import { api } from '../../lib/api'
import { useAsync } from '../../lib/store'
import { cn, titleCase } from '../../lib/utils'
import { Badge, Card, CountUp, Skeleton, stagger } from '../../components/ui'
import { LogoMark } from '../../components/common'

/* ---------- data: read-only GETs, never an AI call ---------- */
export function useEvalSummary() {
  return useAsync(() => api.evaluation().catch(() => null), [])
}
export function useDemoProject(projects) {
  const pick = (projects || []).find((p) => /clinic|login/i.test(p.name) && p.latest_version) || (projects || []).find((p) => p.latest_version)
  const d = useAsync(() => (pick ? api.project(pick.id).catch(() => null) : Promise.resolve(null)), [pick?.id])
  return { project: d.data, loading: d.loading }
}
const leaves = (n, out = []) => { (n?.children || []).forEach((c) => (c.children?.length ? leaves(c, out) : out.push(c))); return out }
const snippet = (files, needle, n) => {
  const lines = (files?.['src/pages/MainPage.jsx'] || '').split('\n')
  const i = lines.findIndex((l) => l.includes(needle))
  return i < 0 ? [] : lines.slice(i, i + n)
}

export function SectionHead({ n, eyebrow, title, desc, action }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="max-w-2xl">
        <div className="mb-3 flex items-center gap-2 font-mono text-[12px] text-accent"><span>{n}</span><span className="h-px w-6 bg-accent/40" /><span className="tracking-wide uppercase">{eyebrow}</span></div>
        <h2 className="text-[26px] leading-[1.15] font-semibold tracking-[-0.03em] sm:text-[30px]">{title}</h2>
        {desc && <p className="mt-3 text-[15px] leading-relaxed text-muted">{desc}</p>}
      </div>
      {action}
    </div>
  )
}
export const Section = ({ className, ...p }) => <section className={cn('mt-20 sm:mt-24', className)} {...p} />

/* ---------- numbers strip ---------- */
export function Numbers({ ev }) {
  const d = ev.data
  const m = d?.metrics
  if (ev.loading) return <div className="mt-16 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line sm:mt-20 md:grid-cols-3 lg:grid-cols-6">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-[132px] rounded-none" />)}</div>
  if (!m) return null
  const c = d.config?.counts || {}
  const pctF = (n) => `${n.toFixed(1)}%`
  const tiles = [
    c.sketches != null && { v: c.sketches, f: (n) => `${Math.round(n)}`, l: 'Test sketches', s: [c.categories && `${c.categories} categories`, c.gt_components && `${c.gt_components} labelled parts`].filter(Boolean).join(' · ') },
    c.commands != null && { v: c.commands, f: (n) => `${Math.round(n)}`, l: 'Voice commands', s: m.whisper_wer ? `${m.whisper_wer.pipeline.toFixed(1)}% Whisper word error` : 'spoken, then transcribed' },
    m.functional_correctness && { v: m.functional_correctness.pipeline, f: pctF, l: 'Functional correctness', s: m.functional_correctness.baseline != null ? `vs ${m.functional_correctness.baseline.toFixed(1)}% direct baseline` : '' },
    m.voice_command_accuracy && { v: m.voice_command_accuracy.pipeline, f: pctF, l: 'Commands understood', s: 'op, target and params, from audio' },
    m.modification_time_ms && { v: m.modification_time_ms.pipeline / 1000, f: (n) => `${n.toFixed(1)} s`, l: 'Per voice edit', s: m.modification_time_ms.baseline != null ? `vs ${(m.modification_time_ms.baseline / 1000).toFixed(1)} s full regeneration` : '' },
    m.preservation_rate && { v: m.preservation_rate.pipeline, f: pctF, l: 'Untouched parts kept', s: 'identical after each edit' },
  ].filter(Boolean)
  return (
    <motion.div {...stagger(2)} className="mt-16 sm:mt-20">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line shadow-xs md:grid-cols-3 lg:grid-cols-6">
        {tiles.map((t) => (
          <div key={t.l} className="flex min-h-[132px] flex-col bg-surface p-5">
            <div className="text-[30px] leading-none font-semibold tracking-[-0.035em] tnum"><CountUp value={t.v} format={t.f} /></div>
            <div className="mt-3 text-[14px] font-medium">{t.l}</div>
            <div className="mt-auto pt-1 text-[12px] leading-snug text-subtle">{t.s}</div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[12px] text-subtle">Measured on the evaluation dataset{d.generated_at ? `, run ${new Date(d.generated_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}. <Link to="/evaluation" className="text-accent hover:underline">All metrics</Link></p>
    </motion.div>
  )
}

/* ---------- pipeline ---------- */
function Wavebars() {
  const h = [6, 14, 9, 22, 12, 28, 16, 24, 10, 18, 7, 20, 11, 15, 6]
  return <div className="flex h-8 items-center gap-[3px]" aria-hidden>{h.map((x, i) => <span key={i} className="w-[3px] rounded-full bg-accent/80" style={{ height: x }} />)}</div>
}
function Mono({ children, className }) {
  return <pre className={cn('overflow-hidden font-mono text-[11.5px] leading-[1.7] whitespace-pre text-muted', className)}>{children}</pre>
}
function Pending({ text = 'Open a generated project to see this step live.' }) {
  return <div className="grid size-full place-items-center px-4 text-center text-[12px] text-subtle">{text}</div>
}

function PipelineFlow({ proj, fallbackSketch }) {
  const v = proj?.latest
  const a = v?.analysis
  const sketch = proj?.sketch_url || fallbackSketch
  const kids = leaves(v?.ir?.pages?.[0]?.root)
  const code = snippet(v?.files, '<Field', 8)
  const checks = v?.validation?.checks || []
  const okN = checks.filter((c) => c.ok).length
  const steps = [
    { t: 'Sketch', d: 'Boxes and labels found in the drawing.', body: sketch ? (
      <div className="flex size-full justify-center bg-white">
        <div className="relative h-full max-w-full" style={{ aspectRatio: a?.width && a?.height ? `${a.width} / ${a.height}` : '4 / 5' }}>
          <img src={sketch} alt="Hand-drawn login sketch from the project" className="size-full object-contain" />
          {a?.components?.filter((c) => c.bbox && c.type !== 'text').map((c, i) => <span key={i} className="absolute rounded-[2px] border border-accent bg-accent/10" style={{ left: `${c.bbox.x * 100}%`, top: `${c.bbox.y * 100}%`, width: `${c.bbox.w * 100}%`, height: `${c.bbox.h * 100}%` }} />)}
        </div>
      </div>
    ) : <Pending text="No sketch yet." /> },
    { t: 'Voice', d: 'Speech becomes a typed edit operation.', body: (
      <div className="flex size-full flex-col justify-center gap-3 p-4">
        <Wavebars />
        <div className="rounded-2xl rounded-tl-md bg-accent-soft px-3 py-2 text-[13px] leading-snug text-accent-soft-fg">Add a phone number field below email.</div>
        <Mono>{'op: add\nrelation: below'}</Mono>
      </div>
    ) },
    { t: 'Fuse', d: 'Geometry and intent merge into one JSON tree.', body: kids.length ? (
      <Mono className="p-4">{`page\n${kids.slice(0, 5).map((k, i, arr) => `${i === arr.length - 1 ? '└' : '├'} ${k.type}${k.label ? ` "${k.label}"` : ''}`).join('\n')}`}</Mono>
    ) : <Pending /> },
    { t: 'Compile', d: 'A deterministic compiler writes React.', body: code.length ? <Mono className="p-4">{code.map((l) => l.replace(/^\s{4}/, '')).join('\n')}</Mono> : <Pending /> },
    { t: 'Verify', d: 'A real browser checks layout and behaviour.', body: checks.length ? (
      <div className="flex size-full flex-col gap-2 p-4">
        {checks.filter((c) => c.ok && c.kind === 'functional').filter((c, i, a) => a.findIndex((d) => d.name === c.name) === i).slice(0, 3).map((c) => <div key={c.id} className="flex items-center gap-2 text-[12.5px]"><span className="grid size-4 shrink-0 place-items-center rounded-full bg-success-soft text-success"><Check className="size-3" strokeWidth={2.6} /></span><span className="truncate">{c.name}</span></div>)}
        <div className="mt-auto flex items-center justify-between"><Badge tone="success" dot>{v.validation.passed ? 'Passed' : 'Reviewed'}</Badge><span className="font-mono text-[12px] text-subtle">{okN}/{checks.length} checks</span></div>
      </div>
    ) : <Pending /> },
  ]
  return (
    <ol className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-5">
      {steps.map((s, i) => (
        <motion.li key={s.t} {...stagger(i, 0.06)} className="relative min-w-0">
          <Card className="flex h-full flex-col overflow-hidden transition-shadow hover:shadow-card">
            <div className="flex items-center gap-2 px-4 pt-4"><span className="font-mono text-[12px] text-accent">{String(i + 1).padStart(2, '0')}</span><span className="text-[15px] font-semibold tracking-tight">{s.t}</span></div>
            <div className="mx-4 mt-3 h-[176px] overflow-hidden rounded-xl border border-line bg-surface-2">{s.body}</div>
            <p className="px-4 pt-3 pb-4 text-[13px] leading-snug text-muted">{s.d}</p>
          </Card>
          {i < 4 && <span className="absolute top-[132px] -right-[19px] z-10 hidden size-[14px] lg:block"><ArrowRight className="size-[14px] text-subtle" /></span>}
        </motion.li>
      ))}
    </ol>
  )
}

export function Pipeline({ proj, fallbackSketch }) {
  return (
    <Section id="pipeline" className="scroll-mt-20">
      <SectionHead n="01" eyebrow="Pipeline" title="Five steps, each one inspectable" desc="Every stage hands a readable artefact to the next, so a spoken change edits the tree instead of rewriting the app. These previews come from a real project." />
      <PipelineFlow proj={proj} fallbackSketch={fallbackSketch} />
    </Section>
  )
}

/* ---------- bento ---------- */
function Tile({ title, desc, className, children, delay = 0 }) {
  return (
    <motion.div {...stagger(delay, 0.05)} className={className}>
      <Card className="flex h-full flex-col p-6 transition-shadow hover:shadow-card">
        <h3 className="text-[16px] font-semibold tracking-tight">{title}</h3>
        <p className="mt-1.5 max-w-md text-[13.5px] leading-relaxed text-muted">{desc}</p>
        <div className="mt-auto pt-6">{children}</div>
      </Card>
    </motion.div>
  )
}
const Stat = ({ v, l }) => <div><div className="text-[22px] leading-none font-semibold tracking-[-0.03em] tnum">{v}</div><div className="mt-1.5 text-[12px] leading-snug text-subtle">{l}</div></div>

export function Bento({ proj, ev }) {
  const v = proj?.latest
  const m = ev.data?.metrics || {}
  const f = (k) => (m[k] ? `${m[k].pipeline.toFixed(1)}%` : null)
  const files = Object.keys(v?.files || {}).filter((k) => k.startsWith('src/') && !k.includes('runtime')).slice(0, 7)
  const code = snippet(v?.files, '<Button', 8)
  const kids = leaves(v?.ir?.pages?.[0]?.root)
  const checks = (v?.validation?.checks || []).filter((c) => c.kind === 'functional').filter((c, i, a) => a.findIndex((d) => d.name === c.name) === i).slice(0, 5)
  const vers = proj?.versions || []
  const bars = [['functional_correctness', 'Functional correctness'], ['requirement_satisfaction', 'Requirement satisfaction'], ['refinement_success_rate', 'Refinement success'], ['preservation_rate', 'Untouched parts kept']].filter(([k]) => m[k])
  return (
    <Section>
      <SectionHead n="02" eyebrow="Capabilities" title="Built to be edited, checked and measured" desc="The output is real code and every change leaves a trail you can inspect." />
      <div className="grid gap-6 lg:grid-cols-12">
        <Tile className="lg:col-span-7" title="Code you can edit" desc="The generated React project is yours: edit any file and the tree stays in sync." delay={0}>
          {code.length ? (
            <div className="grid overflow-hidden rounded-xl border border-line bg-surface-2 sm:grid-cols-[168px_1fr]">
              <div className="hidden border-r border-line p-3 sm:block"><Mono className="text-[11.5px]">{files.map((f2) => f2.replace('src/', '')).join('\n')}</Mono></div>
              <div className="min-w-0 py-3">
                {code.map((l, i) => (
                  <div key={i} className={cn('flex gap-3 px-3 font-mono text-[11.5px] leading-[1.7]', l.includes('#2563eb') ? 'bg-accent-soft text-accent-soft-fg' : 'text-muted')}>
                    <span className="w-3 shrink-0 text-right text-subtle select-none">{i + 1}</span><span className="overflow-hidden whitespace-pre">{l.replace(/^\s{4}/, '')}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <Pending />}
        </Tile>

        <Tile className="lg:col-span-5" title="Voice edits touch one thing" desc="Say what to change. Everything you did not mention stays identical." delay={1}>
          <div className="space-y-2">
            {kids.slice(0, 5).map((k) => {
              const ch = k.type === 'button'
              return (
                <div key={k.id} className={cn('flex items-center gap-2.5 rounded-lg border px-3 py-1.5 font-mono text-[12px]', ch ? 'border-accent/40 bg-accent-soft text-accent-soft-fg' : 'border-line bg-surface-2 text-muted')}>
                  {ch ? <Plus className="size-3.5 shrink-0" /> : <Minus className="size-3.5 shrink-0 text-subtle" />}
                  <span className="truncate">{k.type}{k.label ? ` "${k.label}"` : ''}</span>
                  <span className="ml-auto shrink-0 text-[11.5px]">{ch ? 'background: #2563eb' : 'unchanged'}</span>
                </div>
              )
            })}
            {!kids.length && <Pending />}
          </div>
          {f('preservation_rate') && <div className="mt-5 flex items-end gap-3"><span className="text-[26px] leading-none font-semibold tracking-[-0.03em] tnum">{f('preservation_rate')}</span><span className="pb-0.5 text-[12px] text-subtle">of untouched components preserved across the dataset</span></div>}
        </Tile>

        <Tile className="lg:col-span-5" title="Validation and auto-repair" desc="Every version is opened in a browser. Failed checks are repaired and re-run." delay={2}>
          <div className="space-y-2">
            {checks.map((c) => (
              <div key={c.id} className="flex items-center gap-2.5 text-[12.5px]"><span className={cn('grid size-4 shrink-0 place-items-center rounded-full', c.ok ? 'bg-success-soft text-success' : 'bg-warning-soft text-warning')}><Check className="size-3" strokeWidth={2.6} /></span><span className="truncate">{c.name}</span></div>
            ))}
            {!checks.length && <Pending />}
          </div>
          {(f('validation_pass_rate_after_repair') || f('fault_detection_rate')) && (
            <div className="mt-5 grid grid-cols-3 gap-4 border-t border-line pt-4">
              {f('validation_pass_rate_after_repair') && <Stat v={f('validation_pass_rate_after_repair')} l="pass after repair" />}
              {f('fault_detection_rate') && <Stat v={f('fault_detection_rate')} l="faults detected" />}
              {f('fault_repair_rate') && <Stat v={f('fault_repair_rate')} l="faults repaired" />}
            </div>
          )}
        </Tile>

        <Tile className="lg:col-span-7" title="Version history and compare" desc="Each instruction is a version. Restore any one, or compare two side by side." delay={3}>
          {vers.length ? (
            <div className="grid gap-5 sm:grid-cols-[1.15fr_1fr]">
              <ol className="relative space-y-3.5 pl-6 before:absolute before:top-2 before:bottom-2 before:left-[7px] before:w-px before:bg-line">
                {vers.slice(0, 4).map((x) => (
                  <li key={x.number} className="relative">
                    <span className={cn('absolute top-1 -left-6 grid size-[15px] place-items-center rounded-full border-2 bg-surface', x.passed ? 'border-accent' : 'border-warning')} />
                    <div className="flex items-center gap-2 text-[12px]"><span className="font-mono text-accent">v{x.number}</span><span className="text-subtle">{titleCase(x.kind)}</span>{x.total_ms != null && <span className="ml-auto font-mono text-subtle tnum">{(x.total_ms / 1000).toFixed(1)} s</span>}</div>
                    <div className="mt-0.5 line-clamp-2 text-[13px] leading-snug">{x.text}</div>
                  </li>
                ))}
              </ol>
              <div className="grid grid-cols-2 gap-2">
                {[vers[0], vers[vers.length - 1]].map((x, i) => x?.screenshot_url && (
                  <figure key={i} className="overflow-hidden rounded-xl border border-line bg-surface-2">
                    <img src={x.screenshot_url} alt={`Screenshot of version ${x.number}`} loading="lazy" className="aspect-[4/5] w-full object-cover object-top" />
                    <figcaption className="border-t border-line px-2.5 py-1.5 font-mono text-[11.5px] text-subtle">v{x.number}</figcaption>
                  </figure>
                ))}
              </div>
            </div>
          ) : <Pending />}
        </Tile>

        {bars.length > 0 && (
          <Tile className="lg:col-span-12" title="Measurable evaluation" desc={`Compared with a direct sketch to AI to UI baseline on the same ${ev.data?.config?.counts?.sketches ?? ''} sketches and ${ev.data?.config?.counts?.commands ?? ''} voice commands.`} delay={4}>
            <div className="grid items-end gap-x-10 gap-y-4 md:grid-cols-2">
              {bars.map(([k, l]) => (
                <div key={k}>
                  <div className="mb-1.5 flex items-baseline justify-between text-[13px]"><span>{l}</span><span className="font-mono text-[12px] text-subtle tnum">{m[k].baseline != null && `${m[k].baseline.toFixed(1)}% baseline · `}<span className="text-fg">{m[k].pipeline.toFixed(1)}%</span></span></div>
                  <div className="space-y-1">
                    <motion.div className="h-2 origin-left rounded-full bg-accent" initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }} transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }} style={{ width: `${m[k].pipeline}%` }} />
                    {m[k].baseline != null && <motion.div className="h-2 origin-left rounded-full bg-line-strong" initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }} transition={{ duration: 0.9, delay: 0.1, ease: [0.16, 1, 0.3, 1] }} style={{ width: `${m[k].baseline}%` }} />}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line pt-4 text-[12px] text-subtle"><span className="flex items-center gap-2"><span className="size-2 rounded-full bg-accent" />NeuroGenUI</span><span className="flex items-center gap-2"><span className="size-2 rounded-full bg-line-strong" />Direct baseline</span><Link to="/evaluation" className="ml-auto inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline">Open the evaluation <ArrowUpRight className="size-3.5" /></Link></div>
          </Tile>
        )}
      </div>
    </Section>
  )
}

/* ---------- voice chips ---------- */
const COMMANDS = [
  'Create a login page with email and password fields and a login button.',
  'Add a phone number field below email.',
  'Make the login button blue.',
  'Add a forgot password link below the login button.',
  'Move the button below the password field.',
  'Remove the image.',
  'When the login button is clicked, show an error if the fields are empty.',
]
export function VoiceTry({ onTry, busy }) {
  return (
    <Section>
      <div className="grid items-center gap-8 rounded-3xl border border-line p-6 sm:p-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-12 lg:p-10 paper-grid">
        <div>
          <div className="mb-3 flex items-center gap-2 font-mono text-[12px] text-accent"><span>03</span><span className="h-px w-6 bg-accent/40" /><span className="tracking-wide uppercase">Voice</span></div>
          <h2 className="text-[26px] leading-[1.15] font-semibold tracking-[-0.03em] sm:text-[30px]">Try a voice command</h2>
          <p className="mt-3 max-w-md text-[15px] leading-relaxed text-muted">Pick a phrase. It opens a new project with the command ready in the voice box, so nothing runs until you press send.</p>
        </div>
        <div className="flex flex-wrap content-start gap-2.5">
          {COMMANDS.map((c) => (
            <button key={c} disabled={busy} onClick={() => onTry(c)} className="group inline-flex max-w-full items-center gap-2.5 rounded-full border border-line bg-surface py-2 pr-4 pl-2.5 text-left text-[13.5px] shadow-xs transition-[border-color,box-shadow,transform] duration-300 hover:-translate-y-px hover:border-accent hover:shadow-card disabled:opacity-60">
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent-soft text-accent-soft-fg transition-colors group-hover:bg-accent group-hover:text-accent-fg"><Mic className="size-3.5" /></span>
              <span className="min-w-0">{c.replace(/\.$/, '')}</span>
            </button>
          ))}
        </div>
      </div>
    </Section>
  )
}

/* ---------- footer ---------- */
export function HomeFooter({ ev }) {
  const c = ev.data?.config?.counts
  return (
    <footer className="mt-24 flex flex-col gap-4 border-t border-line pt-8 text-[13px] text-muted sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="flex items-center gap-3"><LogoMark className="size-7 rounded-lg" /><span><span className="font-medium text-fg">NeuroGenUI</span>{c ? `, evaluated on ${c.sketches} sketches and ${c.commands} voice commands` : ', sketch and voice to React'}</span></div>
      <nav className="flex gap-5"><Link to="/dataset" className="hover:text-fg">Dataset</Link><Link to="/evaluation" className="hover:text-fg">Evaluation</Link><a href="#pipeline" className="hover:text-fg">Pipeline</a></nav>
    </footer>
  )
}
export { Sparkles }
