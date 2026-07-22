import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { AntDesignVueResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vite'
import cesium from 'vite-plugin-cesium'

export default defineConfig({
  plugins: [
    vue(),
    cesium(),
    Components({
      resolvers: [AntDesignVueResolver({ importStyle: 'less' })],
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/map-tiles': {
        target: 'https://tile.openstreetmap.de',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(/^\/map-tiles/, ''),
      },
      '/imagery-tiles': {
        target: 'https://server.arcgisonline.com',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(
          /^\/imagery-tiles/,
          '/ArcGIS/rest/services/World_Imagery/MapServer/tile',
        ),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          openlayers: ['ol'],
          antDesign: ['ant-design-vue', '@ant-design/icons-vue'],
        },
      },
    },
  },
})
