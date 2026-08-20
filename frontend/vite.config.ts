import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // 端口可通过环境变量覆盖，便于 dev-dashboard 等场景避免端口冲突
  const apiPort = process.env.API_PORT || (mode === 'intranet' ? '8001' : '8000')
  const webPort = process.env.WEB_PORT || (mode === 'intranet' ? '5174' : '5173')
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: Number(webPort),
      proxy: {
        '/api': `http://localhost:${apiPort}`,
        '/health': `http://localhost:${apiPort}`,
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
  }
})
