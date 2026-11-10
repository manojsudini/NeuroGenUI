import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, Download, FileCode2, FileJson, FileText, Folder, Paintbrush, Play, RotateCcw, Save, Zap } from 'lucide-react'
import { toast } from 'sonner'
import CodeMirror from '@uiw/react-codemirror'
import { javascript } from '@codemirror/lang-javascript'
import { css } from '@codemirror/lang-css'
import { json } from '@codemirror/lang-json'
import { api, errMessage } from '../../lib/api'
import { cn } from '../../lib/utils'
import { Badge, Button, IconButton } from '../../components/ui'
import { cmTheme } from './cmTheme'
import { NotGenerated, useStudio } from './Studio'

const PREVIEW = '⚡ preview.jsx'
const langFor = (p) => (p.endsWith('.css') ? [css()] : p.endsWith('.json') ? [json()] : p.endsWith('.html') ? [] : [javascript({ jsx: true })])
const iconFor = (p) => (p === PREVIEW ? Zap : p.endsWith('.css') ? Paintbrush : p.endsWith('.json') ? FileJson : /\.(jsx?|tsx?)$/.test(p) ? FileCode2 : FileText)

function buildTree(paths) {
  const root = { dirs: {}, files: [] }
  for (const p of paths) {
    const parts = p.split('/')
    let n = root
    for (const d of parts.slice(0, -1)) n = n.dirs[d] ||= { dirs: {}, files: [] }
    n.files.push(p)
  }
  return root
}
function Tree({ node, depth = 0, sel, onSel, edited, prefix = '' }) {
  const [closed, setClosed] = useState({})
  return (
    <>
      {Object.entries(node.dirs).sort().map(([d, sub]) => (
        <div key={d}>
          <button onClick={() => setClosed((c) => ({ ...c, [d]: !c[d] }))} className="flex h-8 w-full items-center gap-1 rounded-md pr-2 text-[13px] text-muted hover:bg-surface-hover" style={{ paddingLeft: 6 + depth * 12 }}>
            <ChevronRight className={cn('size-3 transition-transform', !closed[d] && 'rotate-90')} /><Folder className="size-3.5" />{d}
          </button>
          {!closed[d] && <Tree node={sub} depth={depth + 1} sel={sel} onSel={onSel} edited={edited} prefix={`${prefix}${d}/`} />}
        </div>
      ))}
      {node.files.sort().map((p) => {
        const I = iconFor(p)
        return (
          <button key={p} onClick={() => onSel(p)} title={p} className={cn('flex h-8 w-full items-center gap-2 rounded-md pr-2 text-left text-[13px]', sel === p ? 'bg-accent-soft text-accent-soft-fg' : 'text-fg/85 hover:bg-surface-hover')} style={{ paddingLeft: 18 + depth * 12 }}>
            <I className={cn('size-3.5 shrink-0', sel === p ? 'text-accent' : 'text-subtle')} />
            <span className="truncate">{p.split('/').pop().replace('⚡ ', '')}</span>
            {edited.has(p) && <span className="ml-auto size-1.5 shrink-0 rounded-full bg-warning" title="edited" />}
          </button>
        )
      })}
    </>
  )
}

export default function CodeTab() {
  const s = useStudio()
  const v = s.current
  const [edits, setEdits] = useState({})
  const [sel, setSel] = useState('src/App.jsx')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    setEdits({})
  }, [v?.number])

  const files = useMemo(() => ({ ...(v?.files || {}), ...(v?.preview ? { [PREVIEW]: v.preview } : {}) }), [v])
  const paths = Object.keys(files)
  useEffect(() => {
    if (paths.length && !paths.includes(sel)) setSel(paths.includes('src/App.jsx') ? 'src/App.jsx' : paths[0])
  }, [v?.number]) // eslint-disable-line react-hooks/exhaustive-deps
  const tree = useMemo(() => buildTree(paths.filter((p) => p !== PREVIEW)), [v?.number]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!v) return <NotGenerated what="Generated React source" />
  if (!paths.length) return <div className="p-6 text-[13px] text-muted">This version has no generated files.</div>

  const value = edits[sel] ?? files[sel] ?? ''
  const edited = new Set(Object.keys(edits).filter((k) => edits[k] !== files[k]))
  const loc = value.split('\n').length

  const run = () => {
    s.runCode(edits[PREVIEW] ?? v.preview)
    s.setMobileTab('preview')
    toast('Running edited code in the preview', { description: edited.has(PREVIEW) ? 'Using your edited runtime bundle.' : 'The preview runs preview.jsx. Edit it to try changes live.' })
  }
  const save = async () => {
    setSaving(true)
    try {
      const nextFiles = { ...v.files }
      for (const k of edited) if (k !== PREVIEW) nextFiles[k] = edits[k]
      const nv = await api.putCode(s.id, nextFiles, edits[PREVIEW] ?? v.preview, v.number)
      s.adopt(nv, 'Code saved')
    } catch (e) {
      toast.error('Could not save the code', { description: errMessage(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-4">
        <Button size="xs" variant="dark" icon={Play} onClick={run}>Run</Button>
        <Button size="xs" icon={Save} disabled={!edited.size} loading={saving} onClick={save}>Save as version</Button>
        {edited.size > 0 && <IconButton icon={RotateCcw} label="Discard edits" size="sm" onClick={() => setEdits({})} />}
        <a href={api.exportUrl(s.id, v.number)} download className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-[13px] font-medium shadow-xs hover:bg-surface-hover"><Download className="size-3.5" />Export .zip</a>
      </div>
      <div className="flex min-h-0 flex-1">
        <nav className="w-[34%] max-w-[156px] shrink-0 overflow-y-auto border-r border-line p-1.5" aria-label="Files">
          {v.preview && (
            <>
              <Tree node={{ dirs: {}, files: [PREVIEW] }} sel={sel} onSel={setSel} edited={edited} />
              <div className="my-1.5 h-px bg-line" />
            </>
          )}
          <Tree node={tree} sel={sel} onSel={setSel} edited={edited} />
        </nav>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-9 shrink-0 items-center gap-2 border-b border-line bg-surface-2/60 px-3 font-mono text-[12px] text-muted">
            <span className="truncate">{sel === PREVIEW ? 'runtime bundle (what the iframe runs)' : sel}</span>
            {edited.has(sel) && <Badge tone="warning" >edited</Badge>}
            <span className="ml-auto shrink-0">{loc} lines</span>
          </div>
          <div className="cm-theme min-h-0 flex-1 overflow-hidden">
            <CodeMirror key={sel} value={value} onChange={(x) => setEdits((e) => ({ ...e, [sel]: x }))} extensions={langFor(sel)} theme={cmTheme} height="100%" className="h-full" basicSetup={{ foldGutter: true }} />
          </div>
        </div>
      </div>
      {v.code_stats && (
        <div className="flex shrink-0 flex-wrap gap-x-4 gap-y-1 border-t border-line px-4 py-2.5 font-mono text-[12px] text-subtle">
          {Object.entries(v.code_stats).filter(([, x]) => typeof x !== 'object').map(([k, x]) => <span key={k}>{k} <span className="text-muted">{String(x)}</span></span>)}
        </div>
      )}
    </div>
  )
}
