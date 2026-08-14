import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 代理 API 请求到 Python 搜索服务
    proxy: {
      '/api': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 输出到智能检索工具的 static 目录，替换旧的 index.html
    outDir: '../shared-modules/智能检索工具/static',
    emptyOutDir: false,
  },
})