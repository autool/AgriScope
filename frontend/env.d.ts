/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_CESIUM_3D_TILES_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module 'vue-router' {
  interface RouteMeta {
    title: string
    description: string
    fullWidth?: boolean
    keepAlive?: boolean
  }
}

export {}
