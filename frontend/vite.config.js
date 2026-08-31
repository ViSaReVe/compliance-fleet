import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Relative asset paths. The default '/' only works when the app is served from a
  // domain root; a Cloud Storage object URL serves it from /BUCKET/..., where
  // absolute paths 404 and the page renders blank.
  base: './',
})
