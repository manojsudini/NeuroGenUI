import { ChevronDown } from 'lucide-react'
import { cn } from '../../lib/utils'

/**
 * One consistent step card for the left zone. Exactly one step is open at a time; the closed one keeps a
 * useful summary (thumbnail, counts, last instruction) instead of collapsing to an empty bar.
 */
export function StepCard({ id, n, title, aside, open, onToggle, summary, children }) {
  return (
    <section id={id} className="scroll-mt-20 rounded-2xl border border-line bg-surface shadow-xs">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex min-h-[64px] w-full items-center gap-2.5 rounded-2xl p-4 text-left">
        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent-soft text-[12px] font-medium text-accent-soft-fg tnum">{n}</span>
        <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
        {aside && <div className="ml-auto flex min-w-0 items-center gap-2 text-[13px] text-muted">{aside}</div>}
        <ChevronDown className={cn('size-4 shrink-0 text-subtle transition-transform duration-300', !aside && 'ml-auto', !open && '-rotate-90')} />
      </button>
      {!open && summary && <div className="px-4 pb-4">{summary}</div>}
      <div className={cn('border-t border-line px-4 pt-4 pb-4', !open && 'hidden')}>{children}</div>
    </section>
  )
}
