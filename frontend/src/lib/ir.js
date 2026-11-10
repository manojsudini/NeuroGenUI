import {
  AlignLeft, Box, CircleDot, ClipboardList, CreditCard, FileText, Heading, Image, Link2, List, ListCollapse, Menu, Minus, MousePointerClick, Navigation, PanelTop, Shapes, SquareCheck, TextCursorInput, Type,
} from 'lucide-react'

export const TYPE_ICON = {
  page: FileText, container: Box, card: CreditCard, form: ClipboardList, header: PanelTop, navbar: Menu, nav_item: Navigation, heading: Heading, text: Type, link: Link2,
  button: MousePointerClick, input: TextCursorInput, textarea: AlignLeft, checkbox: SquareCheck, radio: CircleDot, select: ListCollapse, image: Image, list: List, divider: Minus, icon: Shapes,
}
export const typeIcon = (t) => TYPE_ICON[t] || Shapes
export const CONTAINERS = new Set(['page', 'container', 'card', 'form', 'header', 'navbar', 'list'])
export const TYPES = Object.keys(TYPE_ICON)

export const STAGES = [
  { id: 'upload', label: 'Upload' },
  { id: 'analyze_sketch', label: 'Analyze' },
  { id: 'transcribe', label: 'Transcribe' },
  { id: 'interpret', label: 'Interpret' },
  { id: 'fuse', label: 'Fuse' },
  { id: 'codegen', label: 'Codegen' },
  { id: 'validate', label: 'Validate' },
  { id: 'repair', label: 'Repair' },
  { id: 'save', label: 'Save' },
]

export const KIND_TONE = { generate: 'accent', modify: 'info', repair: 'warning', manual_ir: 'neutral', manual_code: 'neutral', restore: 'success' }
export const KIND_LABEL = { generate: 'Generate', modify: 'Modify', repair: 'Repair', manual_ir: 'IR edit', manual_code: 'Code edit', restore: 'Restore' }
export const OP_TONE = { add: 'success', create: 'accent', remove: 'danger', modify: 'info', move: 'warning', resize: 'warning', style: 'accent', interaction: 'info', navigation: 'info' }

/* ---------- Op → readable chip parts ---------- */
const isColor = (v) => typeof v === 'string' && /^(#|rgb|hsl)/i.test(v)
function kv(obj) {
  if (!obj || typeof obj !== 'object') return []
  return Object.entries(obj).map(([k, v]) => ({ k, v: typeof v === 'object' ? JSON.stringify(v) : String(v), color: isColor(v) ? v : null }))
}
export function describeAction(a) {
  if (!a) return ''
  switch (a.type) {
    case 'validate_required': return `require ${(a.targets || []).join(', ')}${a.message ? ` → “${a.message}”` : ''}`
    case 'validate_format': return `check ${a.target} is ${a.format}`
    case 'show_message': return `show “${a.text}”${a.tone ? ` (${a.tone})` : ''}`
    case 'navigate': return `go to ${a.page}`
    case 'toggle_visibility': return `toggle ${a.target}`
    case 'set_text': return `set ${a.target} to “${a.text}”`
    default: return a.type
  }
}
/** {op, target, details:[{k,v,color}]} */
export function opParts(op) {
  const target = op?.target?.ref || op?.target?.id || op?.component?.label || op?.component?.type || op?.page?.name || op?.meta?.title || ''
  const details = []
  if (op.op === 'add' && op.component) details.push({ k: op.component.type, v: op.component.label || '' })
  if (op.position?.relation) details.push({ k: op.position.relation, v: op.position.anchor?.ref || op.position.anchor?.id || '' })
  if (op.changes) {
    if (op.changes.label != null) details.push({ k: 'label', v: `“${op.changes.label}”` })
    details.push(...kv(op.changes.style), ...kv(op.changes.props))
  }
  if (op.scale) details.push({ k: 'scale', v: `×${op.scale}` })
  if (op.event) details.push({ k: `on ${op.event.on}`, v: (op.event.actions || []).map(describeAction).join(' → ') })
  if (op.op === 'navigation' && op.page?.name) details.push({ k: 'to', v: op.page.name })
  if (op.op === 'create') details.push({ k: 'components', v: String((op.components || []).length) })
  return { op: op.op || '?', target, details, confidence: op.confidence }
}

/* ---------- IR traversal ---------- */
export function walk(ir, fn) {
  for (const page of ir?.pages || []) {
    const rec = (node, parent, depth, index) => {
      if (!node) return
      fn(node, { parent, depth, index, page })
      ;(node.children || []).forEach((c, i) => rec(c, node, depth + 1, i))
    }
    rec(page.root, null, 0, 0)
  }
}
export function findNode(ir, id) {
  let hit = null
  walk(ir, (n, ctx) => {
    if (n.id === id) hit = { node: n, ...ctx }
  })
  return hit
}
export function countNodes(ir) {
  let n = 0
  walk(ir, () => n++)
  return n
}

/* ---------- IR diff between two versions ---------- */
const stable = (v) => JSON.stringify(v ?? null, (k, val) => (val && typeof val === 'object' && !Array.isArray(val) ? Object.fromEntries(Object.entries(val).sort()) : val))
export function diffIr(a, b) {
  const map = (ir) => {
    const m = new Map()
    walk(ir, (n, ctx) => m.set(n.id, { n, parent: ctx.parent?.id || null, index: ctx.index, page: ctx.page?.id }))
    return m
  }
  const A = map(a)
  const B = map(b)
  const out = []
  for (const [id, x] of B) {
    const y = A.get(id)
    if (!y) {
      out.push({ id, kind: 'added', type: x.n.type, label: x.n.label, fields: [] })
      continue
    }
    const fields = []
    if ((y.n.label || '') !== (x.n.label || '')) fields.push({ f: 'label', from: y.n.label, to: x.n.label })
    if (y.n.type !== x.n.type) fields.push({ f: 'type', from: y.n.type, to: x.n.type })
    for (const key of ['style', 'props']) {
      const ks = new Set([...Object.keys(y.n[key] || {}), ...Object.keys(x.n[key] || {})])
      for (const k of ks) if (stable(y.n[key]?.[k]) !== stable(x.n[key]?.[k])) fields.push({ f: `${key}.${k}`, from: y.n[key]?.[k], to: x.n[key]?.[k] })
    }
    if (stable(y.n.events) !== stable(x.n.events)) fields.push({ f: 'events', from: `${(y.n.events || []).length} event(s)`, to: `${(x.n.events || []).length} event(s)` })
    if (y.parent !== x.parent || y.index !== x.index) fields.push({ f: 'position', from: `${y.parent ?? 'root'} #${y.index}`, to: `${x.parent ?? 'root'} #${x.index}` })
    if (fields.length) out.push({ id, kind: 'changed', type: x.n.type, label: x.n.label, fields })
  }
  for (const [id, y] of A) if (!B.has(id)) out.push({ id, kind: 'removed', type: y.n.type, label: y.n.label, fields: [] })
  const unchanged = [...B.keys()].filter((id) => A.has(id) && !out.some((o) => o.id === id)).length
  return { changes: out, unchanged }
}

export const fmtVal = (v) => (v == null || v === '' ? '∅' : typeof v === 'object' ? JSON.stringify(v) : String(v))

/* the 7 example commands from the brief (§4.4) */
export const BRIEF_COMMANDS = [
  'Create a login page with email, password and a login button',
  'Add a forgot password link below the login button',
  'Make the login button blue',
  'Move the button below password',
  'Add a phone number field below email',
  'Remove the image',
  'Show an error when login is clicked with empty fields',
]
