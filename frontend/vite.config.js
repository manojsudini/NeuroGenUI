import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const API = 'http://localhost:8200'
// Same-origin in production (FastAPI serves dist at /). In dev, everything backend-ish is proxied to 8200.
const proxied = ['/api', '/runtime', '/files', '/upload-sketch', '/voice-to-text', '/analyze-sketch', '/generate-ui', '/modify-ui', '/validate-ui', '/project/']

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5200,
    strictPort: true,
    proxy: Object.fromEntries(proxied.map((p) => [p, { target: API, changeOrigin: true }])),
  },
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 1600 },
})
