interface ImportMetaEnv {
    readonly VITE_KAKAO_MAP_APP_KEY?: string;
    readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
