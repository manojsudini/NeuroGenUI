import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { motion } from 'motion/react'
import { BarChart3, Database, LayoutGrid, Search } from 'lucide-react'
import { cn } from '../lib/utils'
import { CommandPalette, HealthPill, Logo, ThemeToggle, openCmdK } from './common'
import { IconButton, Kbd } from './ui'

const LINKS = [
  { to: '/', label: 'Projects', icon: LayoutGrid, end: true },
  { to: '/dataset', label: 'Dataset', icon: Database },
  { to: '/evaluation', label: 'Evaluation', icon: BarChart3 },
]

export function TopBar({ children, wide }) {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur-xl backdrop-saturate-150">
      <div className={cn('mx-auto flex h-14 items-center gap-2 px-4 sm:px-6', wide ? 'max-w-none' : 'max-w-[1320px]')}>
        <Logo />
        {children}
        <nav className="ml-4 hidden items-center gap-0.5 md:flex">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => cn('relative rounded-lg px-3.5 py-2 text-[14px] font-medium transition-colors', isActive ? 'text-fg' : 'text-muted hover:text-fg')}>
              {({ isActive }) => (
                <>
                  {isActive && <motion.span layoutId="top-nav" className="absolute inset-0 rounded-lg bg-surface-hover" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
                  <span className="relative">{l.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1.5">
          <button onClick={openCmdK} className="mr-1 hidden h-9 w-56 items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-[13px] text-subtle shadow-xs transition hover:border-line-strong lg:flex">
            <Search className="size-3.5" />Search…<span className="ml-auto flex gap-0.5"><Kbd>Ctrl</Kbd><Kbd>K</Kbd></span>
          </button>
          <div className="lg:hidden"><IconButton icon={Search} label="Search (Ctrl+K)" onClick={openCmdK} /></div>
          <HealthPill className="hidden sm:block" />
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}

export function MobileNav() {
  return (
    <nav className="pb-safe fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-line bg-bg md:hidden">
      {LINKS.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => cn('flex flex-col items-center gap-1 py-3 text-[12px] font-medium', isActive ? 'text-accent' : 'text-muted')}>
          <t.icon className="size-5" strokeWidth={1.8} />{t.label}
        </NavLink>
      ))}
    </nav>
  )
}

export function AppLayout() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [pathname])
  return (
    <div className="min-h-dvh">
      <TopBar />
      <main className="mx-auto max-w-[1320px] px-4 pt-8 pb-28 sm:px-6 md:pb-20">
        <motion.div key={pathname} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}>
          <Outlet />
        </motion.div>
      </main>
      <MobileNav />
      <CommandPalette />
    </div>
  )
}
