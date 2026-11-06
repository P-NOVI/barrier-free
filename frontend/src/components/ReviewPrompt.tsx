import { useState } from 'react';

import { reportKindLabel } from '../lib/reportApi';
import type { RouteReport } from '../lib/routeApi';
import {
    REVIEW_COMMENT_MAX_LENGTH,
    REVIEW_OUTCOMES,
    type ReviewOutcome,
    submitReview,
} from '../lib/reviewApi';

type ReviewPromptProps = {
    /** 경로가 지나간 승인된 제보 */
    reports: RouteReport[];
    onClose: () => void;
};

function ReviewCard({ report }: { report: RouteReport }) {
    const [outcome, setOutcome] = useState<ReviewOutcome | null>(null);
    const [comment, setComment] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [sending, setSending] = useState(false);
    const [done, setDone] = useState(false);

    const handleSubmit = () => {
        if (!outcome || sending) {
            return;
        }
        setSending(true);
        setError(null);
        submitReview(report.id, { outcome, comment })
            .then(() => setDone(true))
            .catch((reason: unknown) =>
                setError(
                    reason instanceof Error
                        ? reason.message
                        : '리뷰를 보내지 못했어요.',
                ),
            )
            .finally(() => setSending(false));
    };

    return (
        <fieldset className="report-form__field review-card">
            <legend>
                {reportKindLabel(report.kind)}
                {report.description && ` · ${report.description}`}
            </legend>
            {done ? (
                <p className="report-form__hint">리뷰를 남겼어요.</p>
            ) : (
                <>
                    <div className="report-form__chips">
                        {REVIEW_OUTCOMES.map((option) => (
                            <button
                                key={option.id}
                                type="button"
                                className="place-info__chip"
                                aria-pressed={outcome === option.id}
                                onClick={() => setOutcome(option.id)}
                            >
                                {option.label}
                            </button>
                        ))}
                    </div>
                    {outcome && (
                        <>
                            <input
                                type="text"
                                className="report-form__textarea review-card__comment"
                                maxLength={REVIEW_COMMENT_MAX_LENGTH}
                                value={comment}
                                placeholder="한마디 (선택)"
                                aria-label="한마디"
                                onChange={(event) =>
                                    setComment(event.target.value)
                                }
                            />
                            <div className="report-form__actions">
                                <button
                                    type="button"
                                    className="report-form__submit"
                                    disabled={sending}
                                    onClick={handleSubmit}
                                >
                                    {sending ? '보내는 중' : '남기기'}
                                </button>
                            </div>
                        </>
                    )}
                    {error && (
                        <p role="alert" className="place-info__error">
                            {error}
                        </p>
                    )}
                </>
            )}
        </fieldset>
    );
}

/** 도착 후 지나온 제보 장소가 어땠는지 묻는다. 남기지 않고 닫아도 된다. */
export default function ReviewPrompt({ reports, onClose }: ReviewPromptProps) {
    return (
        <div className="report-backdrop">
            <section
                className="report-form"
                role="dialog"
                aria-modal="true"
                aria-label="지나온 제보 장소 리뷰"
            >
                <h2 className="report-form__title">도착했어요</h2>
                <p className="report-form__hint">
                    지나온 곳이 제보와 같았나요? 남기지 않고 닫아도 돼요.
                </p>
                {reports.map((report) => (
                    <ReviewCard key={report.id} report={report} />
                ))}
                <div className="report-form__actions">
                    <button
                        type="button"
                        className="place-info__chip report-form__cancel"
                        onClick={onClose}
                    >
                        닫기
                    </button>
                </div>
            </section>
        </div>
    );
}
