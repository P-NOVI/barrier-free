import { useCallback, useEffect, useState } from 'react';

import {
    deleteReport,
    fetchMyReports,
    type Report,
    type ReportUpdate,
    updateReport,
} from '../lib/reportApi';

export type MyReports = {
    reports: Report[];
    /** 처음 불러오기에 실패하면(백엔드·DB가 꺼짐) false */
    available: boolean;
    error: string | null;
    /** 실패하면 오류를 던진다. 부르는 폼이 안내 문구를 보인다. */
    update: (id: number, update: ReportUpdate) => Promise<void>;
    remove: (id: number) => void;
    /** 제보를 새로 올렸거나 로그인·로그아웃으로 사용자가 바뀌면 다시 불러온다. */
    reload: () => void;
};

function messageOf(reason: unknown): string {
    return reason instanceof Error ? reason.message : String(reason);
}

/** 내가 올린 제보 */
export function useMyReports(): MyReports {
    const [reports, setReports] = useState<Report[]>([]);
    const [available, setAvailable] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [version, setVersion] = useState(0);

    useEffect(() => {
        let cancelled = false;
        fetchMyReports()
            .then((found) => {
                if (!cancelled) {
                    setReports(found);
                    setAvailable(true);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setReports([]);
                    setAvailable(false);
                }
            });
        return () => {
            cancelled = true;
        };
    }, [version]);

    const update = useCallback(async (id: number, change: ReportUpdate) => {
        const saved = await updateReport(id, change);
        setReports((current) =>
            current.map((report) => (report.id === id ? saved : report)),
        );
    }, []);

    const remove = useCallback((id: number) => {
        setError(null);
        deleteReport(id)
            .then(() =>
                setReports((current) =>
                    current.filter((report) => report.id !== id),
                ),
            )
            .catch((reason: unknown) => setError(messageOf(reason)));
    }, []);

    const reload = useCallback(() => setVersion((current) => current + 1), []);

    return { reports, available, error, update, remove, reload };
}
