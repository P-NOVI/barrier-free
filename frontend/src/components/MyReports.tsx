import { useState } from 'react';
import { createPortal } from 'react-dom';

import type { MyReports as MyReportsState } from '../hooks/useMyReports';
import { MY_LIST_ICONS as ICONS } from '../lib/myListIcons';
import {
    REPORT_STATUS_LABELS,
    type Report,
    reportKindLabel,
} from '../lib/reportApi';
import MyListRow from './MyListRow';
import ReportEditForm from './ReportEditForm';

type MyReportsProps = {
    reports: MyReportsState['reports'];
    onUpdate: MyReportsState['update'];
    onDelete: MyReportsState['remove'];
};

function titleOf(report: Report): string {
    const label = reportKindLabel(report.kind);
    return report.blocked ? `${label} · 통행 불가` : label;
}

function detailOf(report: Report): string {
    const date = new Date(report.created_at).toLocaleDateString('ko-KR');
    const base = `${REPORT_STATUS_LABELS[report.status]} · ${date}`;
    return report.description ? `${base} · ${report.description}` : base;
}

/** 제보 탭의 내 제보. 검토 중인 제보는 눌러서 고치고, 모든 제보는 지울 수 있다. */
export default function MyReports({
    reports,
    onUpdate,
    onDelete,
}: MyReportsProps) {
    const [editingId, setEditingId] = useState<number | null>(null);
    // 지울지 한 번 더 묻고 있는 제보
    const [confirmingId, setConfirmingId] = useState<number | null>(null);
    // 수정·삭제를 마쳤다고 알리는 팝업의 문구
    const [notice, setNotice] = useState<string | null>(null);

    const list =
        reports.length === 0 ? (
            <p className="my-tab__status">
                위에서 길 위 문제를 제보하면 여기에 모여요.
            </p>
        ) : (
            <ul className="my-list">
                {reports.map((report) => {
                    if (report.id === editingId) {
                        return (
                            <li key={report.id} className="my-report__edit">
                                <ReportEditForm
                                    report={report}
                                    onCancel={() => setEditingId(null)}
                                    onSave={(update) =>
                                        onUpdate(report.id, update).then(() => {
                                            setEditingId(null);
                                            setNotice('수정되었습니다');
                                        })
                                    }
                                />
                            </li>
                        );
                    }
                    if (report.id === confirmingId) {
                        return (
                            <li
                                key={report.id}
                                className="my-list__row my-report__confirm"
                            >
                                <span className="my-report__question">
                                    {titleOf(report)} 제보를 지울까요?
                                </span>
                                <button
                                    type="button"
                                    className="place-info__chip report-form__cancel"
                                    onClick={() => setConfirmingId(null)}
                                >
                                    취소
                                </button>
                                <button
                                    type="button"
                                    className="report-form__submit"
                                    onClick={() => {
                                        setConfirmingId(null);
                                        void onDelete(report.id).then(
                                            (deleted) => {
                                                if (deleted) {
                                                    setNotice('삭제되었습니다');
                                                }
                                            },
                                        );
                                    }}
                                >
                                    지우기
                                </button>
                            </li>
                        );
                    }
                    return (
                        <MyListRow
                            key={report.id}
                            icon={ICONS.flag}
                            title={titleOf(report)}
                            detail={detailOf(report)}
                            onPick={() => {
                                if (report.status === 'pending') {
                                    setEditingId(report.id);
                                }
                            }}
                            onDelete={() => setConfirmingId(report.id)}
                        />
                    );
                })}
            </ul>
        );

    return (
        <>
            {list}
            {notice &&
                // 아래 시트는 transform 으로 움직여서, 그 안의 position: fixed 는 화면이 아니라
                // 시트를 기준으로 놓인다. 화면 가운데에 뜨도록 body 에 그린다.
                createPortal(
                    <div className="report-backdrop">
                        <section
                            className="report-form"
                            role="dialog"
                            aria-modal="true"
                            aria-label={notice}
                        >
                            <div className="my-report__notice">
                                <h2 className="report-form__title">{notice}</h2>
                                <button
                                    type="button"
                                    className="report-form__submit"
                                    autoFocus
                                    onClick={() => setNotice(null)}
                                >
                                    확인
                                </button>
                            </div>
                        </section>
                    </div>,
                    document.body,
                )}
        </>
    );
}
