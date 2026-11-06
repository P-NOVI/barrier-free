import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

const DEFAULT_API_PROXY_TARGET = 'http://127.0.0.1:8000';
// 홈 화면 앱 이름과 색. 색은 index.html 의 theme-color 와 맞춘다.
const APP_NAME = '베리어프리';
const APP_COLOR = '#ffffff';

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
        plugins: [
            react(),
            // 홈 화면에 설치하는 앱(PWA). 서비스워커는 빌드(배포·preview)에서만 켠다.
            VitePWA({
                registerType: 'autoUpdate',
                includeAssets: ['favicon.svg', 'apple-touch-icon-180x180.png'],
                manifest: {
                    name: APP_NAME,
                    short_name: APP_NAME,
                    description: '교통약자를 위한 맞춤 보행 길찾기',
                    lang: 'ko',
                    start_url: '/',
                    scope: '/',
                    display: 'standalone',
                    theme_color: APP_COLOR,
                    background_color: APP_COLOR,
                    icons: [
                        {
                            src: 'pwa-192x192.png',
                            sizes: '192x192',
                            type: 'image/png',
                        },
                        {
                            src: 'pwa-512x512.png',
                            sizes: '512x512',
                            type: 'image/png',
                        },
                        // 로고가 정사각형 가득이라 안드로이드 둥근 아이콘으로 잘라도 된다.
                        {
                            src: 'pwa-512x512.png',
                            sizes: '512x512',
                            type: 'image/png',
                            purpose: 'maskable',
                        },
                    ],
                },
                workbox: {
                    // 화면 파일만 미리 저장한다. /api 는 저장하지 않고, 로그인처럼
                    // /api 로 이동하는 주소를 화면(index.html)으로 바꿔치지 않는다.
                    navigateFallbackDenylist: [/^\/api\//],
                    // 글꼴(Pretendard 조각 파일)은 수가 많아 미리 저장하지 않는다.
                    globPatterns: ['**/*.{js,css,html,svg,png}'],
                },
            }),
        ],
        // 카카오 JavaScript SDK 도메인에 등록한 포트. 이미 쓰이면 다른 포트로 넘어가지 않고 실패한다.
        server: { port: 5173, strictPort: true, proxy },
        preview: { proxy },
    };
});
