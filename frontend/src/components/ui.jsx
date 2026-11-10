import { forwardRef, useEffect, useId, useRef, useState } from 'react'
import { AnimatePresence, animate, motion, useInView } from 'motion/react'
import { AlertTriangle, Check, ChevronDown, Loader2, RefreshCw, WifiOff, X } from 'lucide-react'
import { cn } from '../lib/utils'
import { errMessage } from '../lib/api'

export const EASE = [0.16, 1, 0.3, 1]
export const SPRING = { type: 'spring', stiffness: 500, damping: 38 }

/* ---------- Button ---------- */
const BTN = {
  primary: 'bg-accent text-accent-fg hover:bg-accent-hover shadow-[inset_0_1px_0_rgb(255_255_255/0.18),0_1px_2px_rgb(0_0_0/0.12)]',
  secondary: 'bg-surface text-fg border border-line hover:bg-surface-hover hover:border-line-strong shadow-xs',
  ghost: 'text-muted hover:text-fg hover:bg-surface-hover',
  dark: 'bg-fg text-bg hover:opacity-90',
  danger: 'bg-danger text-white hover:opacity-90',
  'danger-ghost': 'text-danger hover:bg-danger-soft',
  soft: 'bg-accent-soft text-accent-soft-fg hover:brightness-95 dark:hover:brightness-125',
}
const SIZE = { xs: 'h-8 px-3 text-[13px] gap-1.5 rounded-lg', sm: 'h-9 px-3.5 text-[13px] gap-2 rounded-lg', md: 'h-10 px-4 text-[14px] gap-2 rounded-lg', lg: 'h-11 px-5 text-[15px] gap-2 rounded-xl' }

export const Button = forwardRef(function Button({ variant = 'primary', size = 'md', className, icon: Icon, iconRight: IconR, loading, children, disabled, ...p }, ref) {
  return (
    <motion.button ref={ref} whileTap={{ scale: 0.97 }} transition={{ type: 'spring', stiffness: 600, damping: 30 }} disabled={disabled || loading} className={cn('inline-flex shrink-0 select-none items-center justify-center font-medium whitespace-nowrap transition-colors duration-150 disabled:opacity-50', BTN[variant], SIZE[size], className)} {...p}>
      {loading ? <Loader2 className={cn('animate-spin', size === 'lg' ? 'size-[18px]' : 'size-4')} /> : Icon && <Icon className={size === 'lg' ? 'size-[18px]' : 'size-4'} strokeWidth={2} />}
      {children}
      {IconR && <IconR className="size-4" strokeWidth={2} />}
    </motion.button>
  )
})

export const IconButton = forwardRef(function IconButton({ icon: Icon, label, className, size = 'md', active, ...p }, ref) {
  return (
    <button ref={ref} type="button" aria-label={label} title={label} className={cn('inline-grid shrink-0 place-items-center rounded-lg transition-colors disabled:opacity-40', active ? 'bg-accent-soft text-accent-soft-fg' : 'text-muted hover:bg-surface-hover hover:text-fg', size === 'xs' ? 'size-8' : 'size-9', className)} {...p}>
      <Icon className="size-[18px]" strokeWidth={1.8} />
    </button>
  )
})

/* ---------- Badge ---------- */
const TONE = {
  neutral: 'bg-surface-2 text-muted border-line',
  accent: 'bg-accent-soft text-accent-soft-fg border-transparent',
  success: 'bg-success-soft text-success border-transparent',
  warning: 'bg-warning-soft text-warning border-transparent',
  danger: 'bg-danger-soft text-danger border-transparent',
  info: 'bg-info-soft text-info border-transparent',
  solid: 'bg-fg text-bg border-transparent',
}
export function Badge({ tone = 'neutral', dot, className, children, title }) {
  return (
    <span title={title} className={cn('inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium whitespace-nowrap', TONE[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}

/* ---------- Card ---------- */
export function Card({ className, children, ...p }) {
  return <div className={cn('rounded-2xl border border-line bg-surface shadow-xs', className)} {...p}>{children}</div>
}
export function CardHeader({ title, desc, action, className, icon: Icon }) {
  return (
    <div className={cn('flex items-start justify-between gap-4 px-5 pt-5 pb-4', className)}>
      <div className="flex min-w-0 items-start gap-2.5">
        {Icon && <Icon className="mt-0.5 size-4 shrink-0 text-subtle" strokeWidth={1.9} />}
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold tracking-[-0.01em]">{title}</h3>
          {desc && <p className="mt-0.5 text-[13px] text-muted">{desc}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

/* ---------- Inputs ---------- */
const FIELD = 'w-full rounded-lg border border-line bg-surface text-[14px] text-fg shadow-xs transition-[border,box-shadow] outline-none placeholder:text-subtle hover:border-line-strong focus:border-accent focus:ring-4 focus:ring-accent/15 disabled:opacity-60'
export const Input = forwardRef(function Input({ icon: Icon, className, wrapClass, suffix, size = 'md', ...p }, ref) {
  return (
    <div className={cn('group relative flex items-center', wrapClass)}>
      {Icon && <Icon className="pointer-events-none absolute left-3 size-4 text-subtle transition-colors group-focus-within:text-fg" strokeWidth={1.9} />}
      <input ref={ref} className={cn(FIELD, size === 'sm' ? 'h-9 px-3 text-[13px]' : 'h-10 px-3', Icon && 'pl-9', suffix && 'pr-10', className)} {...p} />
      {suffix && <div className="absolute right-2">{suffix}</div>}
    </div>
  )
})
export const Textarea = forwardRef(function Textarea({ className, ...p }, ref) {
  return <textarea ref={ref} className={cn(FIELD, 'min-h-24 px-3 py-2.5 leading-relaxed', className)} {...p} />
})
export function Select({ className, children, size = 'md', wrapClass, ...p }) {
  return (
    <div className={cn('relative', wrapClass)}>
      <select className={cn(FIELD, 'appearance-none pr-8', size === 'sm' ? 'h-9 pl-3 text-[13px]' : 'h-10 pl-3', className)} {...p}>{children}</select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-subtle" />
    </div>
  )
}
export function Field({ label, hint, children, className, aside }) {
  return (
    <div className={cn('block', className)}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-muted">{label}</span>
        {aside}
      </div>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-subtle">{hint}</span>}
    </div>
  )
}
export function Switch({ checked, onChange, label, size = 'md' }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)} className={cn('relative shrink-0 rounded-full transition-colors duration-200', size === 'sm' ? 'h-4 w-7' : 'h-5 w-9', checked ? 'bg-accent' : 'bg-line-strong')}>
      <motion.span layout transition={{ type: 'spring', stiffness: 700, damping: 35 }} className={cn('absolute top-0.5 rounded-full bg-white shadow-sm', size === 'sm' ? 'size-3' : 'size-4', checked ? 'right-0.5' : 'left-0.5')} />
    </button>
  )
}
export function Checkbox({ checked, onChange, label }) {
  return (
    <button type="button" role="checkbox" aria-checked={checked} onClick={() => onChange(!checked)} className="inline-flex items-center gap-2 text-[13px]">
      <span className={cn('grid size-[17px] place-items-center rounded-[5px] border transition-all', checked ? 'border-accent bg-accent text-accent-fg' : 'border-line-strong bg-surface')}>
        <AnimatePresence>{checked && <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}><Check className="size-3" strokeWidth={3.5} /></motion.span>}</AnimatePresence>
      </span>
      {label}
    </button>
  )
}

/* ---------- Segmented / Tabs (shared sliding indicator) ---------- */
export function Segmented({ value, onChange, options, className, size = 'md', full }) {
  const id = useId()
  return (
    <div role="tablist" className={cn('inline-flex rounded-xl border border-line bg-surface-2 p-0.5', full && 'flex w-full', className)}>
      {options.map((o) => {
        const v = o.value ?? o
        const active = v === value
        return (
          <button key={v} role="tab" aria-selected={active} type="button" title={o.title} onClick={() => onChange(v)} className={cn('relative flex items-center justify-center gap-1.5 rounded-[9px] px-2.5 font-medium whitespace-nowrap transition-colors', full && 'flex-1', size === 'xs' ? 'h-7 px-2 text-[12px]' : 'h-8 text-[13px]', active ? 'text-fg' : 'text-muted hover:text-fg')}>
            {active && <motion.span layoutId={`seg-${id}`} transition={SPRING} className="absolute inset-0 rounded-[9px] border border-line bg-surface shadow-xs" />}
            {o.icon && <o.icon className="relative size-3.5" />}
            {(o.label ?? o) !== '' && <span className="relative">{o.label ?? o}</span>}
            {o.count != null && <span className="relative text-[12px] text-subtle tnum">{o.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
export function Tabs({ value, onChange, options, className }) {
  const id = useId()
  return (
    <div role="tablist" className={cn('flex gap-0.5 overflow-x-auto border-b border-line no-scrollbar', className)}>
      {options.map((o) => {
        const v = o.value ?? o
        const active = v === value
        return (
          <button key={v} role="tab" aria-selected={active} type="button" onClick={() => onChange(v)} className={cn('relative -mb-px flex h-12 shrink-0 items-center gap-1.5 px-3.5 text-[13px] font-medium transition-colors', active ? 'text-fg' : 'text-muted hover:text-fg')}>
            {o.icon && <o.icon className={cn('size-4', active && 'text-accent')} strokeWidth={2} />}
            {o.label ?? o}
            {o.count != null && <span className={cn('rounded-full px-1.5 text-[12px] tnum', active ? 'bg-accent-soft text-accent-soft-fg' : 'bg-surface-2 text-muted')}>{o.count}</span>}
            {active && <motion.span layoutId={`tab-${id}`} className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-accent" transition={SPRING} />}
          </button>
        )
      })}
    </div>
  )
}

export const Kbd = ({ children, className }) => <kbd className={cn('inline-flex h-6 min-w-6 items-center justify-center rounded-[5px] border border-line bg-surface-2 px-1 font-mono text-[12px] text-muted', className)}>{children}</kbd>


/* ---------- Popover menu ---------- */
export function Menu({ trigger, children, side = 'bottom', align = 'right', width = 248, className }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const down = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    const key = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', down)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('mousedown', down)
      document.removeEventListener('keydown', key)
    }
  }, [open])
  return (
    <div ref={ref} className="relative">
      {trigger({ open, toggle: () => setOpen((o) => !o), close: () => setOpen(false) })}
      <AnimatePresence>
        {open && (
          <motion.div role="menu" initial={{ opacity: 0, y: side === 'top' ? 6 : -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ duration: 0.16, ease: EASE }} style={{ width }} className={cn('absolute z-40 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-surface p-2 shadow-pop', side === 'top' ? 'bottom-full mb-2' : 'top-full mt-2', align === 'right' ? 'right-0' : 'left-0', className)}>
            {typeof children === 'function' ? children(() => setOpen(false)) : children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
export function MenuLabel({ children }) {
  return <div className="px-2 pt-1 pb-1.5 text-[12px] font-medium tracking-wide text-subtle uppercase">{children}</div>
}
export function MenuItem({ icon: Icon, children, hint, onClick, disabled, trailing, active }) {
  return (
    <button type="button" role="menuitem" disabled={disabled} onClick={onClick} className={cn('flex h-9 w-full items-center gap-2.5 rounded-lg px-2 text-left text-[13px] transition-colors hover:bg-surface-hover disabled:opacity-50', active && 'text-accent-soft-fg')}>
      {Icon && <Icon className="size-4 shrink-0 text-subtle" strokeWidth={1.9} />}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {hint && <span className="text-[12px] text-subtle">{hint}</span>}
      {trailing}
    </button>
  )
}

export function MenuSwitch({ icon: Icon, children, checked, onChange }) {
  return (
    <div className="flex h-9 items-center gap-2.5 rounded-lg px-2 text-[13px]">
      {Icon && <Icon className="size-4 shrink-0 text-subtle" strokeWidth={1.9} />}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      <Switch size="sm" checked={checked} onChange={onChange} label={typeof children === 'string' ? children : 'Toggle'} />
    </div>
  )
}

/* ---------- Animated number ---------- */
export function CountUp({ value, format = (n) => Math.round(n).toLocaleString('en-IN'), duration = 1.1 }) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true })
  useEffect(() => {
    if (!inView || value == null || Number.isNaN(+value)) return
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      if (ref.current) ref.current.textContent = format(value)
      return
    }
    const c = animate(0, +value, { duration, ease: EASE, onUpdate: (v) => ref.current && (ref.current.textContent = format(v)) })
    return () => c.stop()
  }, [inView, value]) // eslint-disable-line react-hooks/exhaustive-deps
  return <span ref={ref} className="tnum">{value == null ? '—' : format(0)}</span>
}

/* ---------- Score ring ---------- */
export function ScoreRing({ value, size = 96, stroke = 8, label }) {
  const v = value == null ? null : Math.max(0, Math.min(1, value > 1 ? value / 100 : value))
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const color = v == null ? 'var(--border-strong)' : v >= 0.85 ? 'var(--success)' : v >= 0.6 ? 'var(--warning)' : 'var(--danger)'
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-2)" strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - (v ?? 0)) }} transition={{ duration: 1, ease: EASE }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-[22px] leading-none font-semibold tracking-[-0.03em] tnum" style={{ fontSize: size * 0.24 }}>{v == null ? '—' : <CountUp value={v * 100} format={(n) => `${Math.round(n)}`} />}</div>
          {label && <div className="mt-1 text-[12px] font-medium tracking-wide text-subtle uppercase">{label}</div>}
        </div>
      </div>
    </div>
  )
}

/* ---------- Progress ---------- */
export function Progress({ value, tone = 'accent', className }) {
  const color = { accent: 'bg-accent', success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger', fg: 'bg-fg', muted: 'bg-line-strong' }[tone]
  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-surface-2', className)}>
      <motion.div initial={{ width: 0 }} animate={{ width: `${Math.max(0, Math.min(100, value))}%` }} transition={{ duration: 0.9, ease: EASE }} className={cn('h-full rounded-full', color)} />
    </div>
  )
}

/* ---------- Skeleton ---------- */
export const Skeleton = ({ className, ...p }) => <div className={cn('shimmer rounded-lg', className)} {...p} />

/* ---------- Overlays ---------- */
export function Modal({ open, onClose, children, className }) {
  useEffect(() => {
    if (!open) return
    const h = (e) => e.key === 'Escape' && onClose()
    addEventListener('keydown', h)
    return () => removeEventListener('keydown', h)
  }, [open, onClose])
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[70] grid place-items-center p-4">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} className="absolute inset-0 bg-black/35 backdrop-blur-[3px]" />
          <motion.div role="dialog" aria-modal="true" initial={{ opacity: 0, scale: 0.96, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.97, y: 4 }} transition={{ type: 'spring', stiffness: 450, damping: 35 }} className={cn('relative max-h-[90dvh] w-full overflow-y-auto rounded-2xl border border-line bg-surface shadow-pop', !/\bmax-w-/.test(className || '') && 'max-w-md', className)}>
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
export function ModalHeader({ title, desc, onClose }) {
  return (
    <div className="flex items-start justify-between gap-4 px-5 pt-5">
      <div>
        <h2 className="text-[16px] font-semibold tracking-tight">{title}</h2>
        {desc && <p className="mt-1 text-[13px] text-muted">{desc}</p>}
      </div>
      <IconButton icon={X} label="Close" size="sm" onClick={onClose} />
    </div>
  )
}

/* ---------- Page header / Empty / Error ---------- */
export function PageHeader({ title, desc, actions, eyebrow }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-2 text-[12px] font-medium tracking-[0.08em] text-subtle uppercase">{eyebrow}</div>}
        <h1 className="text-[24px] leading-tight font-semibold tracking-[-0.025em]">{title}</h1>
        {desc && <p className="mt-1.5 max-w-2xl text-[14px] text-muted">{desc}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
export function Empty({ icon: Icon, title, desc, action, image, compact, className }) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center', compact ? 'px-4 py-8' : 'px-6 py-14', className)}>
      {image ? (
        <div className="mb-5 h-28 w-44 overflow-hidden rounded-2xl border border-line shadow-xs"><img src={image} alt="" className="size-full object-cover" /></div>
      ) : (
        Icon && <div className={cn('mb-3.5 grid place-items-center rounded-2xl border border-line bg-surface-2', compact ? 'size-11' : 'size-14')}><Icon className={cn('text-muted', compact ? 'size-5' : 'size-6')} strokeWidth={1.6} /></div>
      )}
      <h3 className={cn('font-semibold tracking-tight', compact ? 'text-[14px]' : 'text-[15px]')}>{title}</h3>
      {desc && <p className={cn('mt-1 max-w-sm text-muted', compact ? 'text-[13px]' : 'text-[14px]')}>{desc}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
export function ErrorState({ error, onRetry, compact, className }) {
  const offline = error?.offline
  return (
    <Empty compact={compact} className={className} icon={offline ? WifiOff : AlertTriangle} title={offline ? 'Backend not reachable' : error?.noKey ? 'OpenAI key missing' : 'Something went wrong'} desc={errMessage(error)} action={onRetry && <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onRetry}>Try again</Button>} />
  )
}
export function Banner({ tone = 'warning', icon: Icon = AlertTriangle, children, action, onClose, className }) {
  const c = { warning: 'border-warning/30 bg-warning-soft text-warning', danger: 'border-danger/30 bg-danger-soft text-danger', info: 'border-info/30 bg-info-soft text-info', accent: 'border-accent/25 bg-accent-soft text-accent-soft-fg' }[tone]
  return (
    <div className={cn('flex items-start gap-3 rounded-xl border px-4 py-3 text-[13px]', c, className)}>
      <Icon className="mt-px size-4 shrink-0" strokeWidth={2} />
      <div className="min-w-0 flex-1 leading-relaxed text-fg/85">{children}</div>
      {action}
      {onClose && <button onClick={onClose} aria-label="Dismiss" className="-m-0.5 rounded p-0.5 opacity-70 hover:opacity-100"><X className="size-3.5" /></button>}
    </div>
  )
}

/* ---------- Motion helpers ---------- */
export const fadeUp = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.45, ease: EASE } }
export const stagger = (i, base = 0.04) => ({ initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay: Math.min(i, 12) * base, ease: EASE } })
