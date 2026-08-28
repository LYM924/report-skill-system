import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 代理 API 请求到 Python 搜索服务
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 输出到 runtime/static 目录（服务端直接读取此目录）
    outDir: '../../runtime/static',
    emptyOutDir: true,  // 每次构建前清空目录，避免旧版本文件堆积
  },
})