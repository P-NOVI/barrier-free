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
    /** 있으면 JSON 으로 POST 한다. */
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

export async function requestJson<T>(
    { path, query, body, failureMessage }: ApiRequest,
    { baseUrl = import.meta.env.VITE_API_BASE_URL, signal }: ApiOptions = {},
): Promise<T> {
    if (!baseUrl) {
        throw new ApiError(
            'VITE_API_BASE_URL 이 없습니다. frontend/.env 를 확인하세요.',
            'config',
        );
    }
    const url = new URL(path, baseUrl);
    url.search = new URLSearchParams(query).toString();
    const init: RequestInit =
        body === undefined
            ? { signal }
            : {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(body),
                  signal,
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
    return (await response.json()) as T;
}
