import { useState } from 'react';

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

/** My 탭의 내 제보. 검토 중인 제보는 눌러서 고치고, 모든 제보는 지울 수 있다. */
export default function MyReports({
    reports,
    onUpdate,
    onDelete,
}: MyReportsProps) {
    const [editingId, setEditingId] = useState<number | null>(null);
    // 지울지 한 번 더 묻고 있는 제보
    const [confirmingId, setConfirmingId] = useState<number | null>(null);

    if (reports.length === 0) {
        return (
            <p className="my-tab__status">
                지도에서 장소를 눌러 길 위 문제를 제보하면 여기에 모여요.
            </p>
        );
    }

    return (
        <ul className="my-list">
            {reports.map((report) => {
                if (report.id === editingId) {
                    return (
                        <li key={report.id} className="my-report__edit">
                            <ReportEditForm
                                report={report}
                                onCancel={() => setEditingId(null)}
                                onSave={(update) =>
                                    onUpdate(report.id, update).then(() =>
                                        setEditingId(null),
                                    )
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
                                className="place-info__chip"
                                onClick={() => setConfirmingId(null)}
                            >
                                취소
                            </button>
                            <button
                                type="button"
                                className="report-form__submit"
                                onClick={() => {
                                    setConfirmingId(null);
                                    onDelete(report.id);
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
}
