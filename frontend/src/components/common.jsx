import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, BarChart3, CornerDownLeft, Database, FolderOpen, LayoutGrid, Moon, Plus, Search, Sun, SunMoon } from 'lucide-react'
import { toast } from 'sonner'
import { api, errMessage } from '../lib/api'
import { useHealth, useTheme } from '../lib/store'
import { OP_TONE, opParts } from '../lib/ir'
import { ago, cn } from '../lib/utils'
import { Badge, Kbd } from './ui'

export function LogoMark({ className }) {
  return (
    <span className={cn('relative grid size-8 shrink-0 place-items-center overflow-hidden rounded-[10px] bg-accent text-accent-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.25)]', className)}>
      <svg viewBox="0 0 32 32" className="size-[24px] transition-transform duration-500 ease-out-expo group-hover:-rotate-6" fill="none">
        <path d="M7.5 21.5c2.2-6.6 4.6-10 7-10 3 0 1.4 8 4.2 8 1.5 0 2.6-1.8 3.8-4.6" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="23.2" cy="11.6" r="2" fill="currentColor" />
      </svg>
    </span>
  )
}
export function Logo({ compact }) {
  return (
    <Link to="/" className="group flex items-center gap-2.5" aria-label="NeuroGenUI home">
      <LogoMark />
      {!compact && <span className="text-[16px] font-semibold tracking-[-0.03em]">NeuroGen<span className="text-accent">UI</span></span>}
    </Link>
  )
}

export function ThemeToggle({ className }) {
  const { theme, toggle } = useTheme()
  const dark = theme === 'dark'
  return (
    <button onClick={toggle} aria-label="Toggle theme" title={dark ? 'Light mode' : 'Dark mode'} className={cn('relative grid size-9 place-items-center overflow-hidden rounded-lg text-muted transition-colors hover:bg-surface-hover hover:text-fg', className)}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={theme} initial={{ y: -18, opacity: 0, rotate: -90 }} animate={{ y: 0, opacity: 1, rotate: 0 }} exit={{ y: 18, opacity: 0, rotate: 90 }} transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}>
          {dark ? <Moon className="size-[18px]" strokeWidth={1.8} /> : <Sun className="size-[18px]" strokeWidth={1.8} />}
        </motion.span>
      </AnimatePresence>
    </button>
  )
}

/** Live backend status: API reachable, OpenAI key present, validator browser. */
export function HealthPill({ className }) {
  const h = useHealth()
  const [open, setOpen] = useState(false)
  const s = h.state === 'loading' ? { tone: 'neutral', text: 'Checking API' } : h.state === 'offline' ? { tone: 'danger', text: 'API offline' } : h.openai_configured === false ? { tone: 'warning', text: 'No OpenAI key' } : { tone: 'success', text: 'API online' }
  return (
    <div className={cn('relative', className)} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button onClick={() => h.recheck?.()} className="rounded-full"><Badge tone={s.tone} dot>{s.text}</Badge></button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="absolute top-full right-0 z-50 mt-2 w-72 rounded-xl border border-line bg-surface p-3.5 text-[13px] shadow-pop">
            <div className="mb-2 font-semibold">Backend status</div>
            {h.state === 'offline' ? (
              <p className="text-muted">{errMessage(h.error)}</p>
            ) : h.state === 'loading' ? (
              <p className="text-muted">Contacting the API on port 8200…</p>
            ) : (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
                <dt className="text-subtle">OpenAI</dt><dd className={h.openai_configured ? 'text-success' : 'text-warning'}>{h.openai_configured ? 'configured' : 'key missing (vision, Whisper and intent disabled)'}</dd>
                {h.models && Object.entries(h.models).map(([k, v]) => (<Fragment key={k}><dt className="text-subtle">{k}</dt><dd className="truncate font-mono text-[12px]">{String(v)}</dd></Fragment>))}
                <dt className="text-subtle">Validator</dt><dd className="font-mono text-[12px]">{h.browser || '—'}</dd>
              </dl>
            )}
            <div className="mt-2.5 text-[12px] text-subtle">Click the pill to re-check.</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** One parsed Op, as a readable chip: "style · Login button · color ■ #2563eb" */
export function OpChip({ op, className }) {
  const p = opParts(op)
  return (
    <span className={cn('inline-flex h-8 max-w-full min-w-0 items-center gap-2 rounded-lg border border-line bg-surface px-2 text-[13px] leading-tight shadow-xs', className)}>
      <Badge tone={OP_TONE[p.op] || 'neutral'}>{p.op}</Badge>
      {p.target && <span className="truncate font-medium">{p.target}</span>}
      {p.details.slice(0, 2).map((d, i) => (
        <span key={i} className="flex min-w-0 items-center gap-1.5 text-muted">
          <span className="shrink-0">{d.k}</span>
          {d.color && <span className="size-3 shrink-0 rounded-[3px] border border-line" style={{ background: d.color }} />}
          {d.v && <span className="truncate font-mono text-[12px] text-fg/80">{d.v}</span>}
        </span>
      ))}
      {p.confidence != null && <span className="shrink-0 font-mono text-[12px] text-subtle">{Math.round(p.confidence * 100)}%</span>}
    </span>
  )
}

/* ---------- Ctrl+K command palette ---------- */
export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const [projects, setProjects] = useState([])
  const nav = useNavigate()
  const { toggle } = useTheme()

  useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    const o = () => setOpen(true)
    addEventListener('keydown', h)
    addEventListener('ngui:cmdk', o)
    return () => {
      removeEventListener('keydown', h)
      removeEventListener('ngui:cmdk', o)
    }
  }, [])
  useEffect(() => {
    setQ('')
    setSel(0)
    if (open) api.projects().then(setProjects).catch(() => setProjects([]))
  }, [open])

  const newProject = async () => {
    try {
      const p = await api.createProject(`Untitled sketch ${new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`)
      nav(`/p/${p.id}`)
    } catch (e) {
      toast.error('Could not create a project', { description: errMessage(e) })
    }
  }

  const items = useMemo(() => {
    const t = q.trim().toLowerCase()
    const pages = [
      { group: 'Go to', label: 'Projects', icon: LayoutGrid, run: () => nav('/') },
      { group: 'Go to', label: 'Dataset', icon: Database, run: () => nav('/dataset') },
      { group: 'Go to', label: 'Evaluation', icon: BarChart3, run: () => nav('/evaluation') },
    ]
    const actions = [
      { group: 'Actions', label: 'New project', icon: Plus, run: newProject },
      { group: 'Actions', label: 'Toggle light / dark theme', icon: SunMoon, run: () => toggle() },
    ]
    const projs = projects.map((p) => ({ group: 'Projects', label: p.name, sub: `v${p.latest_version ?? 0} · ${ago(p.updated_at)}`, img: p.thumbnail_url || p.sketch_url, icon: FolderOpen, run: () => nav(`/p/${p.id}`) }))
    const all = [...pages, ...actions, ...projs]
    if (!t) return [...pages, ...actions, ...projs.slice(0, 5)]
    return all.filter((i) => i.label.toLowerCase().includes(t)).slice(0, 12)
  }, [q, projects]) // eslint-disable-line react-hooks/exhaustive-deps

  const go = (i) => {
    if (!i) return
    setOpen(false)
    i.run()
  }
  const onKey = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSel((s) => Math.min(items.length - 1, s + 1))
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSel((s) => Math.max(0, s - 1))
    }
    if (e.key === 'Enter') go(items[sel])
  }

  let lastGroup = ''
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[80] flex items-start justify-center px-4 pt-[12vh]">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(false)} className="absolute inset-0 bg-black/30 backdrop-blur-[3px]" />
          <motion.div role="dialog" aria-label="Command palette" initial={{ opacity: 0, scale: 0.97, y: -8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ type: 'spring', stiffness: 500, damping: 38 }} className="relative w-full max-w-xl overflow-hidden rounded-2xl border border-line bg-surface shadow-pop">
            <div className="flex items-center gap-3 border-b border-line px-4">
              <Search className="size-[18px] text-subtle" />
              <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setSel(0) }} onKeyDown={onKey} placeholder="Search projects, pages, actions…" className="h-14 flex-1 bg-transparent text-[15px] outline-none placeholder:text-subtle" />
              <Kbd>ESC</Kbd>
            </div>
            <div className="max-h-[52vh] overflow-y-auto p-2">
              {items.length === 0 && <div className="py-12 text-center text-[14px] text-muted">No results for “{q}”</div>}
              {items.map((it, idx) => {
                const head = it.group !== lastGroup
                lastGroup = it.group
                const I = it.icon
                return (
                  <div key={it.group + it.label + idx}>
                    {head && <div className="px-2.5 pt-3 pb-1.5 text-[12px] font-medium tracking-wide text-subtle uppercase">{it.group}</div>}
                    <button onMouseMove={() => setSel(idx)} onClick={() => go(it)} className={cn('relative flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left text-[14px]', sel === idx ? 'text-fg' : 'text-muted')}>
                      {sel === idx && <motion.span layoutId="cmdk-sel" transition={{ type: 'spring', stiffness: 600, damping: 40 }} className="absolute inset-0 rounded-lg bg-surface-hover" />}
                      <span className="relative grid size-7 shrink-0 place-items-center overflow-hidden rounded-md border border-line bg-surface-2">{it.img ? <img src={it.img} className="size-full object-cover" alt="" /> : I && <I className="size-3.5" />}</span>
                      <span className="relative flex-1 truncate">{it.label}</span>
                      {it.sub && <span className="relative text-[12px] text-subtle tnum">{it.sub}</span>}
                      {sel === idx && <CornerDownLeft className="relative size-3.5 text-subtle" />}
                    </button>
                  </div>
                )
              })}
            </div>
            <div className="flex items-center gap-4 border-t border-line bg-surface-2/60 px-4 py-2.5 text-[12px] text-subtle">
              <span className="flex items-center gap-1.5"><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span>
              <span className="flex items-center gap-1.5"><Kbd>↵</Kbd> open</span>
              <span className="ml-auto flex items-center gap-1">NeuroGenUI <ArrowRight className="size-3" /> quick jump</span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
export const openCmdK = () => dispatchEvent(new Event('ngui:cmdk'))
