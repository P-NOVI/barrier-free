import { type FormEvent, useState } from 'react';

import {
    BLOCKABLE_KIND,
    DESCRIPTION_MAX_LENGTH,
    REPORT_KINDS,
    type Report,
    type ReportKind,
    type ReportUpdate,
} from '../lib/reportApi';

type ReportEditFormProps = {
    report: Report;
    onSave: (update: ReportUpdate) => Promise<void>;
    onCancel: () => void;
};

/** 검토 중인 제보의 유형·통행 여부·설명을 고친다. 위치와 사진은 고칠 수 없다. */
export default function ReportEditForm({
    report,
    onSave,
    onCancel,
}: ReportEditFormProps) {
    const [kind, setKind] = useState<ReportKind>(report.kind);
    const [blocked, setBlocked] = useState(report.blocked);
    const [description, setDescription] = useState(report.description ?? '');
    const [error, setError] = useState<string | null>(null);
    const [sending, setSending] = useState(false);

    const handleSubmit = (event: FormEvent) => {
        event.preventDefault();
        if (sending) {
            return;
        }
        setSending(true);
        setError(null);
        onSave({
            kind,
            blocked: kind === BLOCKABLE_KIND && blocked,
            description: description.trim(),
        }).catch((reason: unknown) => {
            setError(
                reason instanceof Error
                    ? reason.message
                    : '제보를 고치지 못했어요.',
            );
            setSending(false);
        });
    };

    return (
        <form
            className="my-report-edit"
            aria-label="제보 고치기"
            onSubmit={handleSubmit}
        >
            <fieldset className="report-form__field">
                <legend>유형</legend>
                <div className="report-form__chips">
                    {REPORT_KINDS.map((option) => (
                        <button
                            key={option.id}
                            type="button"
                            className="place-info__chip"
                            aria-pressed={kind === option.id}
                            onClick={() => setKind(option.id)}
                        >
                            {option.label}
                        </button>
                    ))}
                </div>
            </fieldset>
            {kind === BLOCKABLE_KIND && (
                <fieldset className="report-form__field">
                    <legend>통행</legend>
                    <div className="report-form__chips">
                        <button
                            type="button"
                            className="place-info__chip"
                            aria-pressed={!blocked}
                            onClick={() => setBlocked(false)}
                        >
                            통행 가능
                        </button>
                        <button
                            type="button"
                            className="place-info__chip"
                            aria-pressed={blocked}
                            onClick={() => setBlocked(true)}
                        >
                            통행 불가
                        </button>
                    </div>
                </fieldset>
            )}
            <label className="report-form__field">
                <span>사진 설명 (선택)</span>
                <textarea
                    className="report-form__textarea"
                    rows={3}
                    maxLength={DESCRIPTION_MAX_LENGTH}
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                />
                <span className="report-form__count">
                    {description.length}/{DESCRIPTION_MAX_LENGTH}
                </span>
            </label>
            <p className="report-form__hint">
                위치와 사진은 고칠 수 없어요. 바꾸려면 지우고 다시 제보해
                주세요.
            </p>
            {error && (
                <p role="alert" className="place-info__error">
                    {error}
                </p>
            )}
            <div className="report-form__actions">
                <button
                    type="button"
                    className="place-info__chip"
                    onClick={onCancel}
                >
                    취소
                </button>
                <button
                    type="submit"
                    className="report-form__submit"
                    disabled={sending}
                >
                    {sending ? '저장 중' : '저장'}
                </button>
            </div>
        </form>
    );
}
