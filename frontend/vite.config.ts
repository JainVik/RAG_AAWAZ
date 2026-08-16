import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_TARGET || 'http://4.213.226.146:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/v1/query/voice': {
        target: process.env.VITE_BACKEND_WS_TARGET || 'ws://4.213.226.146:8000',
        ws: true,
        changeOrigin: true,
      },
      '/ws': {
        target: process.env.VITE_BACKEND_WS_TARGET || 'ws://4.213.226.146:8000',
        ws: true,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ws/, ''),
      },
    },
  },
});
