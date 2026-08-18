import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': mode === 'intranet' ? 'http://localhost:8001' : 'http://localhost:8000',
      '/health': mode === 'intranet' ? 'http://localhost:8001' : 'http://localhost:8000',
    },
  },
  build: {
    outDir: mode === 'intranet' ? 'dist/intranet' : 'dist/internet',
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 1800,
    rollupOptions: {
      input: resolve(__dirname, mode === 'intranet' ? 'intranet.html' : 'internet.html'),
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/maplibre-gl/')) return 'vendor-maplibre'
          if (id.includes('/node_modules/@deck.gl/')) return 'vendor-deck'
          if (id.includes('/node_modules/@loaders.gl/')) return 'vendor-loaders'
          if (id.includes('/node_modules/@math.gl/')) return 'vendor-math'
          if (id.includes('/node_modules/recharts/') || id.includes('/node_modules/d3-')) return 'vendor-charts'
          if (id.includes('/node_modules/world-atlas/') || id.includes('/node_modules/topojson-')) return 'vendor-geo'
        },
      },
    },
  },
}))
