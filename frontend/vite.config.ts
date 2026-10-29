import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    // 카카오 JavaScript SDK 도메인에 등록한 포트. 이미 쓰이면 다른 포트로 넘어가지 않고 실패한다.
    server: { port: 5173, strictPort: true },
});
