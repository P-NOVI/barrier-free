// 도착 후 제보 장소 리뷰. 요청·응답 형식은 backend/app/routers/reports.py 와 같다.

import { type ApiOptions, requestJson } from './apiClient';

// backend/app/schemas.py 의 ReviewRequest.outcome 과 같다.
export const REVIEW_OUTCOMES = [
    { id: 'same', label: '그대로예요' },
    { id: 'improved', label: '나아졌어요' },
    { id: 'gone', label: '없어졌어요' },
] as const;

export type ReviewOutcome = (typeof REVIEW_OUTCOMES)[number]['id'];

// backend/app/models.py 의 REVIEW_COMMENT_MAX_LENGTH 와 같다.
export const REVIEW_COMMENT_MAX_LENGTH = 200;

export type ReviewRequest = {
    outcome: ReviewOutcome;
    /** 비워도 된다. */
    comment?: string;
};

export type Review = {
    id: number;
    report_id: number;
    outcome: ReviewOutcome;
    comment: string;
    created_at: string;
};

/** 같은 제보에 다시 남기면 이전 리뷰를 바꾼다. */
export function submitReview(
    reportId: number,
    { outcome, comment }: ReviewRequest,
    options?: ApiOptions,
): Promise<Review> {
    return requestJson<Review>(
        {
            path: `/api/reports/${reportId}/review`,
            body: { outcome, comment: comment?.trim() ?? '' },
            failureMessage: '리뷰를 보내지 못했습니다.',
        },
        options,
    );
}
