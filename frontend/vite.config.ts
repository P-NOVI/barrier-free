import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

const DEFAULT_API_PROXY_TARGET = 'http://127.0.0.1:8000';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
    // VITE_ 로 시작하지 않는 값도 읽는다. 이 값은 브라우저로 나가지 않는다.
    const env = loadEnv(mode, process.cwd(), '');
    // 화면과 같은 주소(localhost:5173)의 /api 요청을 백엔드로 넘긴다.
    // 같은 사이트가 되어야 게스트·회원 토큰 쿠키가 실린다.
    const proxy = {
        '/api': env.API_PROXY_TARGET || DEFAULT_API_PROXY_TARGET,
    };
    return {
        plugins: [react()],
        // 카카오 JavaScript SDK 도메인에 등록한 포트. 이미 쓰이면 다른 포트로 넘어가지 않고 실패한다.
        server: { port: 5173, strictPort: true, proxy },
        preview: { proxy },
    };
});
