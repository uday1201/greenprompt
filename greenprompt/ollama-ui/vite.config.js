import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  base: '/chat/',
  plugins: [react(),
  tailwindcss(),
  ],
  server: {
    proxy: {
      '/api': {
        open: '/chat',
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
