import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// Backend to proxy to; override with API_TARGET (e.g. a second instance on another port)
const apiTarget = process.env.API_TARGET || 'http://localhost:8000';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      'flowinger': path.resolve(__dirname, './src/flowinger.tsx'),
    },
  },
  server: {
    port: Number(process.env.PORT) || 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', () => {
            // Backend offline or reloading - suppress unhandled error dump
          });
        },
      },
      '/ws': {
        target: apiTarget.replace(/^http/, 'ws'),
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', () => {
            // WebSocket reset during uvicorn reload - suppress EPIPE/ECONNRESET noise
          });
        },
      },
    },
  },
});
