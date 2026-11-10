import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import './index.css'
import App from './App'
import { HealthProvider, ThemeProvider } from './lib/store'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <HealthProvider>
          <MotionConfig reducedMotion="user">
            <App />
          </MotionConfig>
        </HealthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
