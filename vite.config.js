import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8880',
      '/tk-graph': 'http://localhost:8880',
    },
  },
  build: {
    outDir: 'dist',
  },
});
