import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  const apiBase = process.env.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL ?? '/api'
  if (command === 'build' && apiBase !== '/api') {
    throw new Error('La compilación para despliegue requiere VITE_API_BASE_URL=/api. Usa el mismo subdominio para frontend y API.')
  }
  const publicOrigin = command === 'serve' ? env.VITE_PUBLIC_URL : ''
  const backend = 'http://127.0.0.1:8000'
  return {
    plugins: [vue()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      allowedHosts: publicOrigin ? [new URL(publicOrigin).hostname] : [],
      cors: {
        origin: ['http://127.0.0.1:5173', 'http://localhost:5173',
          ...(publicOrigin ? [new URL(publicOrigin).origin] : [])],
      },
      proxy: {
        '/api': {
          target: backend,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/mcp': { target: backend },
        '/oauth': { target: backend },
        '/.well-known': { target: backend },
      },
    },
  }
})
