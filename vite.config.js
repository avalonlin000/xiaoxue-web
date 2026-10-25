import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': process.env.XIAOXUE_API_PROXY || 'http://localhost:8880',
      '/tk-graph': process.env.XIAOXUE_API_PROXY || 'http://localhost:8880',
    },
  },
  build: {
    outDir: 'dist',
  },
});
