import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppLayout } from './components/Layout'
import { useTheme } from './lib/store'
import Projects from './pages/Projects'
import { Empty, Skeleton } from './components/ui'
import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'

const Studio = lazy(() => import('./pages/studio/Studio'))
const Dataset = lazy(() => import('./pages/Dataset'))
const Evaluation = lazy(() => import('./pages/Evaluation'))

function PageLoading() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-56 rounded-2xl" />)}</div>
    </div>
  )
}
function NotFound() {
  return <Empty icon={Compass} title="Page not found" desc="This address doesn’t match any screen in NeuroGenUI." action={<Link to="/" className="text-[13.5px] font-medium text-accent">Back to projects</Link>} />
}

export default function App() {
  const { theme } = useTheme()
  return (
    <>
      <Routes>
        <Route path="/p/:id" element={<Suspense fallback={<div className="p-6"><PageLoading /></div>}><Studio /></Suspense>} />
        <Route element={<AppLayout />}>
          <Route index element={<Projects />} />
          <Route path="/dataset" element={<Suspense fallback={<PageLoading />}><Dataset /></Suspense>} />
          <Route path="/evaluation" element={<Suspense fallback={<PageLoading />}><Evaluation /></Suspense>} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
      <Toaster theme={theme} position="bottom-right" toastOptions={{ style: { fontFamily: 'var(--font-sans)', fontSize: 13, borderRadius: 12, background: 'var(--surface)', color: 'var(--fg)', border: '1px solid var(--border)' } }} />
    </>
  )
}
