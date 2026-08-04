/// <reference types="vite/client" />

// Tipos para import.meta.env de Vite
interface ImportMetaEnv {
  readonly MODE: string
  readonly BASE_URL: string
  readonly PROD: boolean
  readonly DEV: boolean
  readonly SSR: boolean
  readonly VITE_ATLAS_API_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
