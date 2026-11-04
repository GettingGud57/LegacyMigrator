import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './' makes every path relative, so the built site works from any folder or host.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173, host: true },
  preview: { port: 4173, host: true },
});
