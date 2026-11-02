// 백엔드 API 공통 호출. 오류 응답은 FastAPI 형식 {"detail": {"reason", "message"}} 이다.

/** reason 은 백엔드 detail.reason (no_path, search_failed 등) 또는 config · network · http */
export class ApiError extends Error {
    readonly reason: string;

    constructor(message: string, reason: string) {
        super(message);
        this.name = 'ApiError';
        this.reason = reason;
    }
}

export type ApiOptions = { baseUrl?: string; signal?: AbortSignal };

type ApiRequest = {
    path: string;
    query?: Record<string, string>;
    /** 없으면 body 가 있을 때 POST, 없을 때 GET */
    method?: 'POST' | 'PUT' | 'DELETE';
    /** 있으면 JSON 으로 보낸다. */
    body?: unknown;
    /** 오류 응답에 detail 안내 문구가 없을 때 쓰는 문구 */
    failureMessage: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null;
}

async function toApiError(
    response: Response,
    failureMessage: string,
): Promise<ApiError> {
    const body: unknown = await response.json().catch(() => null);
    const detail = isRecord(body) ? body.detail : undefined;
    if (
        isRecord(detail) &&
        typeof detail.message === 'string' &&
        typeof detail.reason === 'string'
    ) {
        return new ApiError(detail.message, detail.reason);
    }
    return new ApiError(`${failureMessage} (HTTP ${response.status})`, 'http');
}

/**
 * VITE_API_BASE_URL 이 비어 있으면 화면과 같은 주소로 보낸다.
 * 개발 중에는 Vite 가 /api 요청을 백엔드로 넘긴다(vite.config.ts 의 proxy).
 * 게스트·회원 토큰 쿠키가 실리려면 화면과 백엔드가 같은 사이트여야 한다.
 */
function resolveBaseUrl(baseUrl: string | undefined): string | undefined {
    return baseUrl || globalThis.location?.origin;
}

/** 이동(링크)으로 여는 API 주소. 예: 카카오·구글 로그인 시작 */
export function apiUrl(
    path: string,
    baseUrl = import.meta.env.VITE_API_BASE_URL,
): string {
    return new URL(path, resolveBaseUrl(baseUrl)).toString();
}

export async function requestJson<T>(
    { path, query, method, body, failureMessage }: ApiRequest,
    { baseUrl = import.meta.env.VITE_API_BASE_URL, signal }: ApiOptions = {},
): Promise<T> {
    const base = resolveBaseUrl(baseUrl);
    if (!base) {
        throw new ApiError(
            'API 주소를 정할 수 없습니다. frontend/.env 의 VITE_API_BASE_URL 을 확인하세요.',
            'config',
        );
    }
    const url = new URL(path, base);
    url.search = new URLSearchParams(query).toString();
    // 게스트·회원 토큰 쿠키(HttpOnly)를 함께 보내고 받는다.
    const credentials: RequestCredentials = 'include';
    const init: RequestInit =
        body === undefined
            ? { method, signal, credentials }
            : {
                  method: method ?? 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(body),
                  signal,
                  credentials,
              };
    let response: Response;
    try {
        response = await fetch(url, init);
    } catch (error) {
        if (signal?.aborted) {
            throw error;
        }
        throw new ApiError(
            '백엔드 서버에 연결하지 못했습니다. 백엔드가 켜져 있는지 확인하세요.',
            'network',
        );
    }
    if (!response.ok) {
        throw await toApiError(response, failureMessage);
    }
    if (response.status === 204) {
        return undefined as T;
    }
    return (await response.json()) as T;
}
