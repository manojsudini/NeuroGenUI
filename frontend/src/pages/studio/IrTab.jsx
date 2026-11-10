import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Braces, ChevronRight, ChevronsDownUp, ChevronsUpDown, Copy, ListTree, Plus, RotateCcw, Save, Trash2, Zap } from 'lucide-react'
import { toast } from 'sonner'
import CodeMirror from '@uiw/react-codemirror'
import { json } from '@codemirror/lang-json'
import { api, errMessage } from '../../lib/api'
import { CONTAINERS, countNodes, describeAction, findNode, typeIcon, walk } from '../../lib/ir'
import { clone, cn } from '../../lib/utils'
import { Badge, Banner, Button, Field, IconButton, Input, Segmented, Select, Switch } from '../../components/ui'
import { cmTheme } from './cmTheme'
import { NotGenerated, useStudio } from './Studio'

function TreeNode({ node, depth, collapsed, toggle, sel, onSelect, onHover }) {
  const Icon = typeIcon(node.type)
  const kids = node.children || []
  const isOpen = !collapsed.has(node.id)
  const active = sel === node.id
  return (
    <li>
      <div
        role="treeitem"
        aria-selected={active}
        aria-expanded={kids.length ? isOpen : undefined}
        tabIndex={0}
        onClick={() => onSelect(node.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onSelect(node.id)
          }
        }}
        onMouseEnter={() => onHover(node.id)}
        onMouseLeave={() => onHover(null)}
        className={cn('group relative flex h-9 cursor-pointer items-center gap-2 rounded-lg pr-2 text-[13px] transition-colors', active ? 'bg-accent-soft text-accent-soft-fg' : 'hover:bg-surface-hover')}
        style={{ paddingLeft: 6 + depth * 14 }}
      >
        {depth > 0 && <span className="absolute top-0 bottom-0 w-px bg-line" style={{ left: depth * 14 - 3 }} />}
        {kids.length ? (
          <button type="button" onClick={(e) => { e.stopPropagation(); toggle(node.id) }} aria-label={isOpen ? 'Collapse' : 'Expand'} className="grid size-4 place-items-center rounded text-subtle hover:text-fg">
            <ChevronRight className={cn('size-3.5 transition-transform duration-200', isOpen && 'rotate-90')} />
          </button>
        ) : (
          <span className="size-4" />
        )}
        <Icon className={cn('size-3.5 shrink-0', active ? 'text-accent' : CONTAINERS.has(node.type) ? 'text-muted' : 'text-fg/80')} strokeWidth={2} />
        <span className={cn('shrink-0 font-medium', CONTAINERS.has(node.type) && 'text-muted')}>{node.type}</span>
        {node.label && <span className="min-w-0 truncate text-muted">“{node.label}”</span>}
        <span className="ml-auto flex shrink-0 items-center gap-1">
          {node.events?.length > 0 && <Zap className="size-3 text-warning" title="has events" />}
          {node.style?.color && <span className="size-2.5 rounded-[3px] border border-line" style={{ background: node.style.color }} />}
          {node.origin && node.origin !== 'sketch' && <span className="font-mono text-[12px] text-subtle">{node.origin}</span>}
        </span>
      </div>
      {kids.length > 0 && isOpen && (
        <ul role="group">
          {kids.map((c) => <TreeNode key={c.id} node={c} depth={depth + 1} collapsed={collapsed} toggle={toggle} sel={sel} onSelect={onSelect} onHover={onHover} />)}
        </ul>
      )}
    </li>
  )
}

const VARIANTS = ['', 'primary', 'secondary', 'outline', 'ghost', 'danger']
const INPUT_TYPES = ['text', 'email', 'password', 'tel', 'number', 'date', 'search']
const PHOTOS = ['', 'person', 'product', 'banner', 'food', 'travel', 'building', 'finance', 'nature']
const toHex = (c) => (typeof c === 'string' && /^#[0-9a-f]{6}$/i.test(c) ? c : typeof c === 'string' && /^#[0-9a-f]{3}$/i.test(c) ? `#${[...c.slice(1)].map((x) => x + x).join('')}` : '#000000')

function ColorField({ label, value, onChange }) {
  return (
    <Field label={label}>
      <div className="flex items-center gap-1.5">
        <label className="relative size-8 shrink-0 overflow-hidden rounded-lg border border-line shadow-xs" style={{ background: value || 'transparent' }}>
          {!value && <span className="checker absolute inset-0" />}
          <input type="color" value={toHex(value)} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" aria-label={`${label} picker`} />
        </label>
        <Input size="sm" value={value || ''} placeholder="none" onChange={(e) => onChange(e.target.value)} className="font-mono text-[12px]" />
      </div>
    </Field>
  )
}

function PropertyForm({ node, onApply, saving }) {
  const [d, setD] = useState(() => clone(node))
  useEffect(() => setD(clone(node)), [node])
  const set = (path, v) =>
    setD((x) => {
      const n = clone(x)
      const [a, b] = path.split('.')
      if (b) {
        n[a] = { ...(n[a] || {}) }
        if (v === '' || v == null) delete n[a][b]
        else n[a][b] = v
      } else n[a] = v
      return n
    })
  const dirty = JSON.stringify(d) !== JSON.stringify(node)
  const t = node.type
  const st = d.style || {}
  const pr = d.props || {}
  const widthMode = st.width == null ? '' : typeof st.width === 'number' ? 'px' : st.width
  const [newMsg, setNewMsg] = useState('')

  return (
    <div className="space-y-3.5 p-4">
      <div className="flex items-center gap-2">
        <Badge tone="accent" className="font-mono">{node.id}</Badge>
        <span className="text-[12px] text-subtle">{t}{node.origin ? ` · from ${node.origin}` : ''}</span>
      </div>

      {t !== 'divider' && (
        <Field label={t === 'image' ? 'Caption / label' : 'Label'}>
          <Input size="sm" aria-label="Node label" value={d.label || ''} onChange={(e) => set('label', e.target.value)} />
        </Field>
      )}

      <div className="text-[12px] font-medium tracking-wide text-subtle uppercase">Style</div>
      <div className="grid grid-cols-2 gap-3">
        {['button', 'link', 'nav_item'].includes(t) && (
          <Field label="Variant">
            <Select size="sm" value={st.variant || ''} onChange={(e) => set('style.variant', e.target.value)}>{VARIANTS.map((v) => <option key={v} value={v}>{v || 'default'}</option>)}</Select>
          </Field>
        )}
        <ColorField label="Color" value={st.color} onChange={(v) => set('style.color', v)} />
        <ColorField label="Text color" value={st.textColor} onChange={(v) => set('style.textColor', v)} />
        {CONTAINERS.has(t) && <ColorField label="Background" value={st.bg} onChange={(v) => set('style.bg', v)} />}
        <Field label="Width">
          <div className="flex gap-1.5">
            <Select size="sm" value={widthMode} onChange={(e) => set('style.width', e.target.value === 'px' ? 240 : e.target.value)}>
              <option value="">default</option><option value="auto">auto</option><option value="full">full</option><option value="px">px</option>
            </Select>
            {widthMode === 'px' && <Input size="sm" type="number" min={20} max={2000} value={st.width} onChange={(e) => set('style.width', e.target.value ? +e.target.value : '')} className="w-20 font-mono" />}
          </div>
        </Field>
        <Field label="Size">
          <Select size="sm" value={st.size || ''} onChange={(e) => set('style.size', e.target.value)}><option value="">default</option><option value="sm">sm</option><option value="md">md</option><option value="lg">lg</option></Select>
        </Field>
      </div>
      <Field label="Align">
        <Segmented size="xs" value={st.align || ''} onChange={(v) => set('style.align', v)} options={[{ value: '', label: 'default' }, { value: 'left', label: 'left' }, { value: 'center', label: 'center' }, { value: 'right', label: 'right' }]} />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Font px"><Input size="sm" type="number" min={8} max={96} value={st.fontSize ?? ''} onChange={(e) => set('style.fontSize', e.target.value ? +e.target.value : '')} className="font-mono" /></Field>
        <Field label="Weight">
          <Select size="sm" value={st.fontWeight ?? ''} onChange={(e) => set('style.fontWeight', e.target.value ? +e.target.value : '')}><option value="">—</option>{[400, 500, 600, 700].map((w) => <option key={w} value={w}>{w}</option>)}</Select>
        </Field>
        <Field label="Radius"><Input size="sm" type="number" min={0} max={64} value={st.radius ?? ''} onChange={(e) => set('style.radius', e.target.value ? +e.target.value : '')} className="font-mono" /></Field>
      </div>
      <label className="flex items-center justify-between text-[13px] text-muted">Hidden<Switch size="sm" checked={!!st.hidden} onChange={(v) => set('style.hidden', v || '')} label="Hidden" /></label>

      {['input', 'textarea', 'select', 'heading', 'image', 'list', 'checkbox', 'radio'].includes(t) && <div className="pt-1 text-[12px] font-medium tracking-wide text-subtle uppercase">Props</div>}
      {(t === 'input' || t === 'textarea') && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Placeholder" className="col-span-2"><Input size="sm" value={pr.placeholder || ''} onChange={(e) => set('props.placeholder', e.target.value)} /></Field>
          {t === 'input' && <Field label="Input type"><Select size="sm" value={pr.inputType || 'text'} onChange={(e) => set('props.inputType', e.target.value)}>{INPUT_TYPES.map((x) => <option key={x}>{x}</option>)}</Select></Field>}
          <Field label="Required"><div className="flex h-8 items-center"><Switch checked={!!pr.required} onChange={(v) => set('props.required', v)} label="Required" /></div></Field>
        </div>
      )}
      {t === 'heading' && <Field label="Level"><Segmented size="xs" value={pr.level || 2} onChange={(v) => set('props.level', v)} options={[1, 2, 3, 4].map((l) => ({ value: l, label: `H${l}` }))} /></Field>}
      {t === 'select' && <Field label="Options" hint="Comma separated"><Input size="sm" value={(pr.options || []).join(', ')} onChange={(e) => set('props.options', e.target.value.split(',').map((x) => x.trim()).filter(Boolean))} /></Field>}
      {t === 'list' && <Field label="Items" hint="Comma separated"><Input size="sm" value={(pr.items || []).join(', ')} onChange={(e) => set('props.items', e.target.value.split(',').map((x) => x.trim()).filter(Boolean))} /></Field>}
      {(t === 'checkbox' || t === 'radio') && <label className="flex items-center justify-between text-[13px] text-muted">Checked<Switch size="sm" checked={!!pr.checked} onChange={(v) => set('props.checked', v)} label="Checked" /></label>}
      {t === 'image' && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Photo"><Select size="sm" value={pr.photo || ''} onChange={(e) => set('props.photo', e.target.value)}>{PHOTOS.map((p) => <option key={p} value={p}>{p || 'placeholder'}</option>)}</Select></Field>
          <Field label="Alt text"><Input size="sm" value={pr.alt || ''} onChange={(e) => set('props.alt', e.target.value)} /></Field>
        </div>
      )}

      <div className="pt-1 text-[12px] font-medium tracking-wide text-subtle uppercase">Events</div>
      <div className="space-y-1.5">
        {(d.events || []).length === 0 && <p className="text-[12px] text-subtle">No events. Voice commands like “show an error when login is clicked with empty fields” add them.</p>}
        {(d.events || []).map((ev, i) => (
          <div key={i} className="flex items-start gap-2 rounded-lg border border-line bg-surface-2/60 px-2.5 py-2 text-[12px]">
            <Badge tone="warning" className="shrink-0 font-mono">on {ev.on}</Badge>
            <ol className="min-w-0 flex-1 space-y-0.5 text-muted">{(ev.actions || []).map((a, j) => <li key={j} className="break-words"><span className="font-mono text-[12px] text-subtle">{j + 1}.</span> {describeAction(a)}</li>)}</ol>
            <IconButton icon={Trash2} label="Remove event" size="xs" onClick={() => set('events', d.events.filter((_, k) => k !== i))} />
          </div>
        ))}
        {['button', 'link', 'nav_item', 'form'].includes(t) && (
          <div className="flex gap-1.5">
            <Input size="sm" value={newMsg} onChange={(e) => setNewMsg(e.target.value)} placeholder="Message to show on click…" />
            <Button size="sm" variant="secondary" icon={Plus} disabled={!newMsg.trim()} onClick={() => { set('events', [...(d.events || []), { on: t === 'form' ? 'submit' : 'click', actions: [{ type: 'show_message', text: newMsg.trim(), tone: 'info' }] }]); setNewMsg('') }}>Add</Button>
          </div>
        )}
      </div>

      <div className="sticky bottom-0 -mx-4 mt-2 flex items-center gap-2 border-t border-line bg-surface/95 px-4 py-3 backdrop-blur">
        <span className="text-[12px] text-subtle">{dirty ? 'Unsaved changes' : 'No changes'}</span>
        <Button size="sm" variant="ghost" icon={RotateCcw} disabled={!dirty} onClick={() => setD(clone(node))} className="ml-auto">Reset</Button>
        <Button size="sm" icon={Save} disabled={!dirty} loading={saving} onClick={() => onApply(d)}>Save as version</Button>
      </div>
    </div>
  )
}

export default function IrTab() {
  const s = useStudio()
  const v = s.current
  const [view, setView] = useState('tree')
  const [collapsed, setCollapsed] = useState(new Set())
  const [saving, setSaving] = useState(false)
  const scrollRef = useRef(null)
  const formRef = useRef(null)
  const ir = v?.ir
  const hit = useMemo(() => (ir && s.selectedId ? findNode(ir, s.selectedId) : null), [ir, s.selectedId])
  const total = useMemo(() => (ir ? countNodes(ir) : 0), [ir])
  const irText = useMemo(() => (ir ? JSON.stringify(ir, null, 2) : ''), [ir])

  const stats = useMemo(() => {
    const tally = {}
    const events = []
    let interactive = 0
    if (ir) walk(ir, (n) => {
      tally[n.type] = (tally[n.type] || 0) + 1
      if (n.events?.length) {
        interactive++
        for (const ev of n.events) events.push({ node: n, ev })
      }
    })
    return { tally: Object.entries(tally).sort((a, b) => b[1] - a[1]), events, interactive }
  }, [ir])

  useEffect(() => {
    if (hit) setTimeout(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 80)
  }, [hit?.node?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!v) return <NotGenerated what="The UI intent tree" />
  if (!ir) return <div className="p-6 text-[13px] text-muted">This version has no IR (code-only edit).</div>

  const toggle = (id) => setCollapsed((c) => {
    const n = new Set(c)
    n.has(id) ? n.delete(id) : n.add(id)
    return n
  })
  const allIds = () => {
    const ids = []
    const rec = (n) => { if (n.children?.length) ids.push(n.id); n.children?.forEach(rec) }
    ir.pages.forEach((p) => rec(p.root))
    return ids
  }
  const hover = (id) => s.highlight(id)

  const apply = async (draft) => {
    setSaving(true)
    try {
      const next = clone(ir)
      const h = findNode(next, draft.id)
      if (!h) throw new Error('Node not found in the IR')
      Object.assign(h.node, { label: draft.label, style: draft.style || {}, props: draft.props || {}, events: draft.events || [] })
      if (!h.node.origin || h.node.origin === 'sketch' || h.node.origin === 'voice') h.node.origin = 'manual'
      const nv = await api.patchIr(s.id, next, v.number)
      s.adopt(nv, 'IR updated')
    } catch (e) {
      toast.error('Could not save the IR change', { description: errMessage(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-4">
        <Segmented size="xs" value={view} onChange={setView} options={[{ value: 'tree', label: 'Tree', icon: ListTree }, { value: 'json', label: 'JSON', icon: Braces }]} />
        <span className="truncate text-[12px] text-subtle">{ir.meta?.title || 'Untitled'}</span>
        <div className="ml-auto flex">
          {view === 'tree' ? (
            <>
              <IconButton icon={ChevronsDownUp} label="Collapse all" size="xs" onClick={() => setCollapsed(new Set(allIds()))} />
              <IconButton icon={ChevronsUpDown} label="Expand all" size="xs" onClick={() => setCollapsed(new Set())} />
            </>
          ) : (
            <IconButton icon={Copy} label="Copy JSON" size="xs" onClick={() => navigator.clipboard?.writeText(irText).then(() => toast.success('IR copied'))} />
          )}
        </div>
      </div>
      {v.ir_synced === false && <Banner tone="warning" className="m-4 mb-0">This version was edited as code, so the IR may not match the preview. Saving an IR change regenerates the code from the IR.</Banner>}

      {view === 'json' ? (
        <div className="cm-theme min-h-0 flex-1 overflow-hidden">
          <CodeMirror value={irText} editable={false} extensions={[json()]} theme={cmTheme} height="100%" basicSetup={{ foldGutter: true, highlightActiveLine: false }} className="h-full" />
        </div>
      ) : (
        <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <div className="grid grid-cols-3 gap-3">
            {[['Nodes', total], ['Pages', ir.pages?.length || 0], ['Interactive', stats.interactive]].map(([k, n]) => (
              <div key={k} className="rounded-xl border border-line bg-surface-2/50 px-3 py-3">
                <div className="text-[20px] leading-none font-semibold tracking-[-0.02em] tnum">{n}</div>
                <div className="mt-1.5 text-[12px] text-muted">{k}</div>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-line p-2">
            {ir.pages.map((p) => (
              <div key={p.id}>
                {ir.pages.length > 1 && <div className="px-2 pt-1 pb-1 text-[12px] font-medium tracking-wide text-subtle uppercase">{p.name} <span className="font-mono normal-case">{p.route}</span></div>}
                <ul role="tree" aria-label={`Components of ${p.name}`}>
                  <TreeNode node={p.root} depth={0} collapsed={collapsed} toggle={toggle} sel={s.selectedId} onSelect={(id) => s.setSelectedId(id === s.selectedId ? null : id)} onHover={hover} />
                </ul>
              </div>
            ))}
          </div>

          <AnimatePresence mode="wait">
            {hit ? (
              <motion.div key={hit.node.id} ref={formRef} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} className="-mx-4 -mb-4 border-t border-line">
                <PropertyForm node={hit.node} onApply={apply} saving={saving} />
              </motion.div>
            ) : (
              <motion.div key="overview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                <section>
                  <h3 className="mb-2 text-[13px] font-medium text-muted">Component mix</h3>
                  <ul className="space-y-2">
                    {stats.tally.map(([t, n]) => {
                      const I = typeIcon(t)
                      return (
                        <li key={t} className="flex items-center gap-3 text-[13px]">
                          <I className="size-4 shrink-0 text-subtle" strokeWidth={1.9} />
                          <span className="w-20 shrink-0">{t}</span>
                          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2"><span className="block h-full rounded-full bg-accent/70" style={{ width: `${(n / stats.tally[0][1]) * 100}%` }} /></span>
                          <span className="w-5 text-right font-mono text-[12px] text-muted tnum">{n}</span>
                        </li>
                      )
                    })}
                  </ul>
                </section>
                <section>
                  <h3 className="mb-2 text-[13px] font-medium text-muted">Behaviour</h3>
                  {stats.events.length === 0 ? (
                    <p className="text-[13px] text-subtle">No interactions yet. Try “show an error when login is clicked with empty fields”.</p>
                  ) : (
                    <ul className="space-y-2">
                      {stats.events.map(({ node, ev }, i) => (
                        <li key={i} className="flex items-start gap-2.5 rounded-lg border border-line bg-surface-2/50 px-3 py-2.5 text-[13px]">
                          <Zap className="mt-0.5 size-4 shrink-0 text-warning" />
                          <span className="min-w-0 text-muted"><span className="text-fg">on {ev.on} of {node.label ? `“${node.label}”` : node.type}</span>: {(ev.actions || []).map(describeAction).join(', ')}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
                <p className="text-[12px] text-subtle">Hover a node to outline it in the preview. Click it to edit its properties.</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
