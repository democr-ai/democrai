import path from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

import { viteSingleFile } from 'vite-plugin-singlefile'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    viteSingleFile({ useRecommendedBuildConfig: true, removeViteModuleLoader: true }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    cssCodeSplit: false,
    assetsInlineLimit: () => true,
    assetsDir: '',
    target: 'es2015', // Importante per la compatibilità
  },
  base: './',
})
