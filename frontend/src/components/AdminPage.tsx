import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { type ReviewAction, useAdminReports } from '../hooks/useAdminReports';
import {
    type AdminReport,
    isReportExpired,
    reportPhotoUrl,
} from '../lib/adminApi';
import { ApiError } from '../lib/apiClient';
import type { LngLat } from '../lib/kakaoMap';
import {
    REPORT_STATUS_LABELS,
    type ReportStatus,
    reportKindLabel,
} from '../lib/reportApi';
import MapView from './MapView';

function formatTime(value: string): string {
    return new Date(value).toLocaleString('ko-KR', {
        dateStyle: 'medium',
        timeStyle: 'short',
    });
}

// 대기 → 승인 → 해결됨 → 취소 순서로 탭을 보인다.
const TABS: { status: ReportStatus; label: string; empty: string }[] = [
    {
        status: 'pending',
        label: '대기',
        empty: '검토를 기다리는 제보가 없어요.',
    },
    { status: 'approved', label: '승인', empty: '승인한 제보가 없어요.' },
    {
        status: 'resolved',
        label: '해결됨',
        empty: '해결됨으로 바꾼 제보가 없어요.',
    },
    { status: 'rejected', label: '취소', empty: '취소한 제보가 없어요.' },
];

const QUESTIONS: Record<ReviewAction, string> = {
    approve: '승인하시겠습니까?',
    cancel: '취소하시겠습니까?',
    resolve: '해결됨으로 처리하시겠습니까?',
};

function accessMessage(error: Error): string {
    if (error instanceof ApiError && error.reason === 'login_required') {
        return '로그인한 뒤에 다시 열어 주세요. 지도 화면에서 로그인할 수 있어요.';
    }
    if (error instanceof ApiError && error.reason === 'admin_only') {
        return '관리자 계정만 열 수 있는 화면이에요.';
    }
    return error.message;
}

type ReportCardProps = {
    report: AdminReport;
    /** 대기 중이면 승인·취소, 승인했으면 해결됨 처리를 할 수 있다. */
    status: ReportStatus;
    /** 만료 여부를 가르는 현재 시각(ms) */
    now: number;
    busy: boolean;
    onReview: (action: ReviewAction) => void;
};

function ReportCard({ report, status, now, busy, onReview }: ReportCardProps) {
    const [mapOpen, setMapOpen] = useState(false);
    const position: LngLat = [report.lon, report.lat];
    // 서버도 만료된 제보의 승인을 막는다. 여기서는 눌러 보기 전에 알려 준다.
    const expired = isReportExpired(report, now);
    return (
        <li className="admin-page__card">
            <a
                className="admin-page__photo-link"
                href={reportPhotoUrl(report)}
                target="_blank"
                rel="noreferrer"
            >
                <img
                    className="admin-page__photo"
                    src={reportPhotoUrl(report)}
                    alt={`${reportKindLabel(report.kind)} 제보 사진`}
                    loading="lazy"
                />
            </a>
            <div className="admin-page__body">
                <h2 className="admin-page__title">
                    {reportKindLabel(report.kind)}
                    {report.blocked && (
                        <span className="admin-page__badge">통행 불가</span>
                    )}
                    {expired && (
                        <span className="admin-page__badge admin-page__badge--expired">
                            만료됨
                        </span>
                    )}
                    <span className="admin-page__status">
                        {REPORT_STATUS_LABELS[report.status]}
                    </span>
                </h2>
                <p className="admin-page__description">
                    {report.description ?? '설명 없음'}
                </p>
                <dl className="admin-page__facts">
                    <dt>위치</dt>
                    <dd>
                        {report.lat.toFixed(5)}, {report.lon.toFixed(5)}{' '}
                        <button
                            type="button"
                            className="admin-page__map-toggle"
                            aria-expanded={mapOpen}
                            onClick={() => setMapOpen((open) => !open)}
                        >
                            {mapOpen ? '지도 닫기' : '지도에서 보기'}
                        </button>
                    </dd>
                    <dt>제보</dt>
                    <dd>{formatTime(report.created_at)}</dd>
                    <dt>만료</dt>
                    <dd>{formatTime(report.expires_at)}</dd>
                </dl>
                {status === 'approved' && (
                    <div className="admin-page__actions">
                        <button
                            type="button"
                            className="admin-page__cancel"
                            disabled={busy}
                            onClick={() => onReview('resolve')}
                        >
                            해결됨 처리
                        </button>
                    </div>
                )}
                {status === 'pending' && (
                    <div className="admin-page__actions">
                        <button
                            type="button"
                            className="admin-page__approve"
                            disabled={busy || expired}
                            title={
                                expired
                                    ? '만료된 제보는 승인할 수 없어요'
                                    : undefined
                            }
                            onClick={() => onReview('approve')}
                        >
                            승인
                        </button>
                        <button
                            type="button"
                            className="admin-page__cancel"
                            disabled={busy}
                            onClick={() => onReview('cancel')}
                        >
                            취소
                        </button>
                    </div>
                )}
            </div>
            {mapOpen && (
                <div className="admin-page__map">
                    <MapView center={position} picked={position} />
                </div>
            )}
        </li>
    );
}

/** /admin. 대기 제보를 승인·취소하고, 승인한 제보는 해결됨으로 바꾸며, 처리한 제보도 따로 본다. */
export default function AdminPage() {
    const [status, setStatus] = useState<ReportStatus>('pending');
    const { reports, loading, loadError, reviewError, review, reload } =
        useAdminReports(status);
    // 열어 둔 채로 만료되는 제보도 표시가 바뀌도록 현재 시각을 1분마다 갱신한다.
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 60_000);
        return () => clearInterval(timer);
    }, []);
    const tab = TABS.find((item) => item.status === status) ?? TABS[0];
    const [busyId, setBusyId] = useState<number | null>(null);

    // 승인·취소는 되돌릴 수 없어서, 누르면 먼저 한 번 더 묻는다.
    const [asking, setAsking] = useState<{
        id: number;
        action: ReviewAction;
    } | null>(null);

    const handleReview = (id: number, action: ReviewAction) => {
        setBusyId(id);
        void review(id, action).finally(() => setBusyId(null));
    };

    const question = asking && QUESTIONS[asking.action];

    let content;
    if (loading) {
        content = <p className="admin-page__status-text">불러오는 중이에요.</p>;
    } else if (loadError) {
        content = (
            <p className="admin-page__error" role="alert">
                {accessMessage(loadError)}
            </p>
        );
    } else if (reports.length === 0) {
        content = <p className="admin-page__status-text">{tab.empty}</p>;
    } else {
        content = (
            <ul className="admin-page__list">
                {reports.map((report) => (
                    <ReportCard
                        key={report.id}
                        report={report}
                        status={status}
                        now={now}
                        busy={busyId === report.id}
                        onReview={(action) =>
                            setAsking({ id: report.id, action })
                        }
                    />
                ))}
            </ul>
        );
    }

    return (
        <main className="admin-page">
            <header className="admin-page__header">
                <h1 className="admin-page__heading">제보 검토</h1>
                <span className="admin-page__count">
                    {loading || loadError
                        ? ''
                        : `${reports.length}건 ${tab.label}`}
                </span>
                <button
                    type="button"
                    className="admin-page__refresh"
                    onClick={reload}
                >
                    새로고침
                </button>
                <a className="admin-page__back" href="/">
                    지도로
                </a>
            </header>
            <div className="admin-page__tabs" role="tablist">
                {TABS.map((item) => (
                    <button
                        key={item.status}
                        type="button"
                        role="tab"
                        aria-selected={item.status === status}
                        className="admin-page__tab"
                        onClick={() => setStatus(item.status)}
                    >
                        {item.label}
                    </button>
                ))}
            </div>
            {reviewError && (
                <p className="admin-page__error" role="alert">
                    {reviewError}
                </p>
            )}
            {content}
            {asking &&
                createPortal(
                    <div className="report-backdrop">
                        <section
                            className="report-form"
                            role="dialog"
                            aria-modal="true"
                            aria-label={question ?? undefined}
                        >
                            <h2 className="report-form__title">{question}</h2>
                            <p className="report-form__hint">
                                처리하면 되돌릴 수 없어요.
                            </p>
                            <div className="report-form__actions">
                                <button
                                    type="button"
                                    className="place-info__chip report-form__cancel"
                                    autoFocus
                                    onClick={() => setAsking(null)}
                                >
                                    아니요
                                </button>
                                <button
                                    type="button"
                                    className="report-form__submit"
                                    onClick={() => {
                                        handleReview(asking.id, asking.action);
                                        setAsking(null);
                                    }}
                                >
                                    예
                                </button>
                            </div>
                        </section>
                    </div>,
                    document.body,
                )}
        </main>
    );
}
