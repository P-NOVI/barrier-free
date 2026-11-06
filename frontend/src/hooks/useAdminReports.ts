import { useCallback, useEffect, useState } from 'react';

import {
    type AdminReport,
    approveReport,
    cancelReport,
    fetchReports,
    resolveReport,
} from '../lib/adminApi';
import { ApiError } from '../lib/apiClient';
import type { ReportStatus } from '../lib/reportApi';

/** 승인 · 취소는 대기 제보에, 해결됨은 승인한 제보에 쓴다. */
export type ReviewAction = 'approve' | 'cancel' | 'resolve';

const REVIEWS = {
    approve: approveReport,
    cancel: cancelReport,
    resolve: resolveReport,
};

export type AdminReports = {
    reports: AdminReport[];
    loading: boolean;
    /** 불러오지 못했을 때. reason 이 login_required·admin_only 면 권한 문제 */
    loadError: Error | null;
    /** 승인·취소·해결됨 처리에 실패한 문구 */
    reviewError: string | null;
    /** 처리를 마친 제보는 지금 목록에서 빠진다. 실패하면 reviewError 에 문구를 담는다. */
    review: (id: number, action: ReviewAction) => Promise<void>;
    reload: () => void;
};

type Loaded = { key: string; reports: AdminReport[]; error: Error | null };

function asError(reason: unknown): Error {
    return reason instanceof Error ? reason : new Error(String(reason));
}

/**
 * 상태별 제보. 대기 제보는 오래된 것부터, 승인·취소한 제보는 나중에 올라온 것부터 보인다.
 * status 가 바뀌거나 reload 를 부르면 다시 불러온다.
 */
export function useAdminReports(status: ReportStatus): AdminReports {
    const [loaded, setLoaded] = useState<Loaded | null>(null);
    const [reviewError, setReviewError] = useState<string | null>(null);
    const [version, setVersion] = useState(0);
    const key = `${status}:${version}`;

    useEffect(() => {
        let cancelled = false;
        fetchReports(status)
            .then((found) => {
                if (!cancelled) {
                    const reports =
                        status === 'pending' ? found : found.toReversed();
                    setLoaded({ key, reports, error: null });
                }
            })
            .catch((reason: unknown) => {
                if (!cancelled) {
                    setLoaded({ key, reports: [], error: asError(reason) });
                }
            });
        return () => {
            cancelled = true;
        };
    }, [status, key]);

    const dropReport = useCallback((id: number) => {
        setLoaded(
            (current) =>
                current && {
                    ...current,
                    reports: current.reports.filter((r) => r.id !== id),
                },
        );
    }, []);

    const review = useCallback(
        async (id: number, action: ReviewAction) => {
            setReviewError(null);
            try {
                await REVIEWS[action](id);
            } catch (reason) {
                setReviewError(asError(reason).message);
                // 다른 관리자가 먼저 처리했을 수 있어, 이 목록에서는 뺀다.
                if (
                    reason instanceof ApiError &&
                    (reason.reason === 'report_not_pending' ||
                        reason.reason === 'report_not_approved')
                ) {
                    dropReport(id);
                }
                return;
            }
            dropReport(id);
        },
        [dropReport],
    );

    const reload = useCallback(() => setVersion((current) => current + 1), []);

    // 탭을 바꾸거나 새로고침해서 key 가 바뀌면 새 결과가 올 때까지 불러오는 중이다.
    const current = loaded?.key === key ? loaded : null;
    return {
        reports: current?.reports ?? [],
        loading: current === null,
        loadError: current?.error ?? null,
        reviewError,
        review,
        reload,
    };
}
