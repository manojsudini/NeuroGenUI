import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, Clock, FolderPlus, GitBranch, ImageOff, Layers, PenLine, Plus, Search, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { api, errMessage } from '../lib/api'
import { useAsync } from '../lib/store'
import { ago, cn, titleCase } from '../lib/utils'
import HeroDemo from './home/HeroDemo'
import { Bento, HomeFooter, Numbers, Pipeline, Section, SectionHead, VoiceTry, useDemoProject, useEvalSummary } from './home/Sections'
import { Badge, Button, Card, Empty, ErrorState, Field, IconButton, Input, Modal, ModalHeader, Skeleton, stagger } from '../components/ui'

function Hero({ onNew, onSamples }) {
  return (
    <section className="relative grid grid-cols-1 items-center gap-10 pt-2 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-16 lg:pt-8">
      <div aria-hidden className="bg-grid mask-fade-b pointer-events-none absolute inset-x-0 -top-8 -z-10 h-[520px] opacity-70" />
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}>
        <Badge tone="accent" className="mb-6"><PenLine className="size-3" />Sketch + voice to React</Badge>
        <h1 className="max-w-xl text-[40px] leading-[1.05] font-semibold tracking-[-0.04em] sm:text-[52px]">Draw it.<br />Say it.<br />Edit the UI.</h1>
        <p className="mt-6 max-w-md text-[16px] leading-relaxed text-muted">Sketch a screen, speak a change, and get real React you can open, check and compare. Each edit touches only what you named.</p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button size="lg" icon={Plus} onClick={onNew}>New project</Button>
          <Button size="lg" variant="secondary" iconRight={ArrowRight} onClick={onSamples}>Start from a sample</Button>
        </div>
      </motion.div>
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}>
        <HeroDemo />
      </motion.div>
    </section>
  )
}

function Samples({ onPick, busyId, s }) {
  const shown = (s.data || []).slice(0, 12)
  return (
    <section id="samples" className="mt-20 scroll-mt-20 sm:mt-24">
      <SectionHead n="04" eyebrow="Quick start" title="Start from a test sketch" desc="Pick one from the evaluation dataset. It opens a new project with the sketch on the canvas." action={s.data?.length > 12 && <Link to="/dataset" className="inline-flex items-center gap-1.5 text-[14px] font-medium text-accent hover:underline">Browse all {s.data.length} <ArrowRight className="size-4" /></Link>} />
      {s.loading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="aspect-[4/5] rounded-2xl" />)}</div>
      ) : s.error ? (
        <Card><ErrorState compact error={s.error} onRetry={s.reload} /></Card>
      ) : !s.data?.length ? (
        <Card><Empty compact icon={ImageOff} title="No sample sketches yet" desc="The dataset folder has no sketches yet. They appear here once dataset/sketches is generated." /></Card>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          {shown.map((x, i) => (
            <motion.button key={x.id} {...stagger(i, 0.03)} onClick={() => onPick(x)} disabled={!!busyId} className="group relative overflow-hidden rounded-2xl border border-line bg-surface text-left transition-[box-shadow,border-color] hover:border-line-strong hover:shadow-card disabled:opacity-60">
              <div className="aspect-[4/3] overflow-hidden border-b border-line bg-white">
                <img src={x.url} alt={x.title} loading="lazy" className="size-full object-contain p-3 transition-transform duration-700 ease-out-expo group-hover:scale-[1.05]" />
              </div>
              <div className="px-4 py-3">
                <div className="truncate text-[14px] font-medium">{x.title || titleCase(x.id)}</div>
                <div className="mt-0.5 text-[12px] text-subtle">{titleCase(x.category)}</div>
              </div>
              {busyId === x.id && <div className="absolute inset-0 grid place-items-center bg-surface/70 text-[13px] font-medium">Opening…</div>}
            </motion.button>
          ))}
        </div>
      )}
    </section>
  )
}

function ProjectCard({ p, i, onDelete }) {
  const shot = p.thumbnail_url && p.thumbnail_url !== p.sketch_url ? p.thumbnail_url : null
  return (
    <motion.div layout {...stagger(i, 0.04)} exit={{ opacity: 0, scale: 0.97 }} className="group relative overflow-hidden rounded-2xl border border-line bg-surface transition-[box-shadow,border-color] duration-300 hover:border-line-strong hover:shadow-card">
      <Link to={`/p/${p.id}`} className="block">
        <div className="grid aspect-[16/10] grid-cols-2 gap-px overflow-hidden border-b border-line bg-line">
          <div className="relative overflow-hidden bg-white">
            {p.sketch_url ? <img src={p.sketch_url} alt="" loading="lazy" className="size-full object-contain p-2 transition-transform duration-700 ease-out-expo group-hover:scale-[1.05]" /> : <div className="paper-grid grid size-full place-items-center text-[12px] text-subtle"><PenLine className="size-5" strokeWidth={1.5} /></div>}
            <span className="absolute bottom-3 left-3 rounded-md bg-black/55 px-2 py-0.5 text-[12px] font-medium text-white">Sketch</span>
          </div>
          <div className="relative overflow-hidden bg-surface-2">
            {shot ? <img src={shot} alt="" loading="lazy" className="size-full object-cover object-top transition-transform duration-700 ease-out-expo group-hover:scale-[1.05]" /> : <div className="grid size-full place-items-center px-3 text-center text-[12px] text-subtle">{p.latest_version ? 'No screenshot yet' : 'Not generated yet'}</div>}
            <span className="absolute bottom-3 left-3 rounded-md bg-accent px-2 py-0.5 text-[12px] font-medium text-accent-fg">UI</span>
          </div>
        </div>
        <div className="p-4 pr-14">
          <h3 className="truncate text-[15px] font-semibold tracking-tight">{p.name}</h3>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted">
            <span className="flex items-center gap-1"><GitBranch className="size-3.5" />{p.versions ?? 0} version{p.versions === 1 ? '' : 's'}</span>
            <span className="flex items-center gap-1"><Clock className="size-3.5" />{ago(p.updated_at || p.created_at)}</span>
          </div>
        </div>
      </Link>
      <IconButton icon={Trash2} label="Delete project" size="sm" onClick={() => onDelete(p)} className="absolute right-3 bottom-3 opacity-60 hover:!bg-danger-soft hover:!text-danger group-hover:opacity-100" />
    </motion.div>
  )
}

export default function Projects() {
  const nav = useNavigate()
  const list = useAsync(() => api.projects(), [])
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [pickBusy, setPickBusy] = useState(null)
  const [toDelete, setToDelete] = useState(null)
  const [q, setQ] = useState('')
  const ev = useEvalSummary()
  const samples = useAsync(() => api.samples(), [])
  const demo = useDemoProject(list.data)

  const create = async (e) => {
    e?.preventDefault()
    setBusy(true)
    try {
      const p = await api.createProject(name.trim() || 'Untitled sketch')
      nav(`/p/${p.id}`)
    } catch (err) {
      toast.error('Could not create the project', { description: errMessage(err) })
    } finally {
      setBusy(false)
    }
  }
  const pickSample = async (s) => {
    setPickBusy(s.id)
    try {
      const p = await api.createProject(s.title || titleCase(s.id))
      nav(`/p/${p.id}?sample=${encodeURIComponent(s.url)}${s.instruction ? `&say=${encodeURIComponent(s.instruction)}` : ''}`)
    } catch (err) {
      toast.error('Could not start from this sample', { description: errMessage(err) })
      setPickBusy(null)
    }
  }
  const tryCommand = async (text) => {
    setPickBusy('cmd')
    try {
      const p = await api.createProject('Voice command')
      nav(`/p/${p.id}?say=${encodeURIComponent(text)}`)
    } catch (err) {
      toast.error('Could not open a project', { description: errMessage(err) })
      setPickBusy(null)
    }
  }
  const del = async () => {
    const p = toDelete
    setToDelete(null)
    try {
      await api.deleteProject(p.id)
      list.setData((d) => (d || []).filter((x) => x.id !== p.id))
      toast.success('Project deleted', { description: p.name })
    } catch (err) {
      toast.error('Delete failed', { description: errMessage(err) })
    }
  }

  const projects = (list.data || []).filter((p) => p.name.toLowerCase().includes(q.trim().toLowerCase()))

  return (
    <div>
      <Hero onNew={() => setCreating(true)} onSamples={() => document.getElementById('samples')?.scrollIntoView({ behavior: 'smooth' })} />
      <Numbers ev={ev} />
      <Pipeline proj={demo.project} fallbackSketch={samples.data?.find((x) => /login/.test(x.id))?.url} />
      <Bento proj={demo.project} ev={ev} />
      <VoiceTry onTry={tryCommand} busy={!!pickBusy} />
      <Samples onPick={pickSample} busyId={pickBusy} s={samples} />

      <Section id="projects" className="scroll-mt-20">
        <SectionHead n="05" eyebrow="Workspace" title="Your projects" desc={list.data ? `${list.data.length} project${list.data.length === 1 ? '' : 's'}, each with its sketch and the generated UI` : 'Your sketches and the UIs generated from them'} action={
          <div className="flex items-center gap-2">
            {list.data?.length > 3 && <Input icon={Search} size="sm" placeholder="Filter projects" value={q} onChange={(e) => setQ(e.target.value)} wrapClass="w-52" />}
            <Button size="sm" variant="secondary" icon={FolderPlus} onClick={() => setCreating(true)}>New project</Button>
          </div>} />
        {list.loading && !list.data ? (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2, 3].map((i) => <div key={i} className="overflow-hidden rounded-2xl border border-line bg-surface"><Skeleton className="aspect-[16/10] rounded-none" /><div className="space-y-2 p-4"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-1/2" /></div></div>)}</div>
        ) : list.error ? (
          <Card><ErrorState error={list.error} onRetry={list.reload} /></Card>
        ) : !list.data?.length ? (
          <Card className="overflow-hidden">
            <Empty image="/img/markers-sketch.jpg" title="No projects yet" desc="Start with a blank canvas, or pick one of the sample sketches above to see the full pipeline run." action={<Button icon={Plus} onClick={() => setCreating(true)}>Create your first project</Button>} />
          </Card>
        ) : projects.length === 0 ? (
          <Card><Empty compact icon={Search} title="No matches" desc={`No project name contains “${q}”.`} /></Card>
        ) : (
          <motion.div layout className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence>{projects.map((p, i) => <ProjectCard key={p.id} p={p} i={i} onDelete={setToDelete} />)}</AnimatePresence>
            {!q && <button onClick={() => setCreating(true)} className="group grid min-h-[240px] place-items-center rounded-2xl border border-dashed border-line-strong text-center text-muted transition-colors hover:border-accent hover:bg-accent-soft/40 hover:text-accent-soft-fg"><span><span className="mx-auto mb-3 grid size-11 place-items-center rounded-full border border-line-strong bg-surface transition-colors group-hover:border-accent"><Plus className="size-5" /></span><span className="text-[14px] font-medium">New project</span><span className="mt-1 block text-[13px]">Start from a blank canvas</span></span></button>}
          </motion.div>
        )}
      </Section>

      <HomeFooter ev={ev} />

      <Modal open={creating} onClose={() => setCreating(false)}>
        <form onSubmit={create}>
          <ModalHeader title="New project" desc="A project keeps the sketch, every instruction and every generated version." onClose={() => setCreating(false)} />
          <div className="px-5 py-4">
            <Field label="Project name"><Input autoFocus placeholder="e.g. Clinic booking — login" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></Field>
          </div>
          <div className="flex justify-end gap-2 border-t border-line bg-surface-2/60 px-5 py-3.5">
            <Button type="button" variant="secondary" onClick={() => setCreating(false)}>Cancel</Button>
            <Button type="submit" loading={busy} icon={Layers}>Create and open</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!toDelete} onClose={() => setToDelete(null)}>
        <ModalHeader title="Delete this project?" desc={`“${toDelete?.name}” and all of its versions, sketches and screenshots will be removed. This can’t be undone.`} onClose={() => setToDelete(null)} />
        <div className="mt-4 flex justify-end gap-2 border-t border-line bg-surface-2/60 px-5 py-3.5">
          <Button variant="secondary" onClick={() => setToDelete(null)}>Cancel</Button>
          <Button variant="danger" icon={Trash2} onClick={del}>Delete project</Button>
        </div>
      </Modal>
    </div>
  )
}
