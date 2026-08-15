import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8082',
      '/health': 'http://localhost:8082',
      '/version': 'http://localhost:8082',
      '/metrics': 'http://localhost:8082',
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  }
})
