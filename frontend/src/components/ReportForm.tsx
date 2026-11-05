import { type ChangeEvent, type FormEvent, useState } from 'react';

import type { LngLat } from '../lib/kakaoMap';
import {
    BLOCKABLE_KIND,
    DESCRIPTION_MAX_LENGTH,
    PHOTO_MAX_BYTES,
    REPORT_KINDS,
    type ReportKind,
    submitReport,
} from '../lib/reportApi';

type ReportFormProps = {
    position: LngLat;
    /** 지도에서 누른 곳의 주소. 없으면 좌표만 제보한다. */
    address?: string | null;
    onClose: () => void;
};

const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export default function ReportForm({
    position,
    address,
    onClose,
}: ReportFormProps) {
    const [kind, setKind] = useState<ReportKind>('curb');
    const [blocked, setBlocked] = useState(false);
    const [photo, setPhoto] = useState<File | null>(null);
    const [description, setDescription] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [sending, setSending] = useState(false);
    const [done, setDone] = useState(false);

    const handlePhoto = (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0] ?? null;
        setPhoto(null);
        if (!file) {
            setError(null);
        } else if (!PHOTO_TYPES.includes(file.type)) {
            setError('JPEG, PNG, WebP 사진만 올릴 수 있어요.');
        } else if (file.size > PHOTO_MAX_BYTES) {
            setError('사진은 5MB 이하만 올릴 수 있어요.');
        } else {
            setError(null);
            setPhoto(file);
        }
    };

    const handleSubmit = (event: FormEvent) => {
        event.preventDefault();
        if (!photo || sending) {
            return;
        }
        setSending(true);
        setError(null);
        submitReport({ kind, blocked, position, photo, description })
            .then(() => setDone(true))
            .catch((reason: unknown) =>
                setError(
                    reason instanceof Error
                        ? reason.message
                        : '제보를 보내지 못했어요.',
                ),
            )
            .finally(() => setSending(false));
    };

    return (
        <div className="report-backdrop">
            <section
                className="report-form"
                role="dialog"
                aria-modal="true"
                aria-label="길 위 문제 제보"
            >
                {done ? (
                    <>
                        <h2 className="report-form__title">제보했어요</h2>
                        <p className="report-form__hint">
                            관리자가 사진을 확인하면 지도에 표시돼요.
                        </p>
                        <div className="report-form__actions">
                            <button
                                type="button"
                                className="report-form__submit"
                                onClick={onClose}
                            >
                                닫기
                            </button>
                        </div>
                    </>
                ) : (
                    <form onSubmit={handleSubmit}>
                        <h2 className="report-form__title">길 위 문제 제보</h2>
                        <p className="report-form__hint">
                            {address ?? '선택한 위치'}
                        </p>
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
                            <span>사진 (필수)</span>
                            <input
                                type="file"
                                accept={PHOTO_TYPES.join(',')}
                                onChange={handlePhoto}
                            />
                        </label>
                        <label className="report-form__field">
                            <span>사진 설명 (선택)</span>
                            <textarea
                                className="report-form__textarea"
                                rows={3}
                                maxLength={DESCRIPTION_MAX_LENGTH}
                                value={description}
                                placeholder="예: 보도 끝에 10cm 턱이 있어요"
                                onChange={(event) =>
                                    setDescription(event.target.value)
                                }
                            />
                            <span className="report-form__count">
                                {description.length}/{DESCRIPTION_MAX_LENGTH}
                            </span>
                        </label>
                        <p className="report-form__hint">
                            얼굴이나 차량 번호판이 나오지 않게 찍어 주세요.
                            사진은 관리자만 볼 수 있어요.
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
                                onClick={onClose}
                            >
                                취소
                            </button>
                            <button
                                type="submit"
                                className="report-form__submit"
                                disabled={!photo || sending}
                            >
                                {sending ? '보내는 중' : '제보하기'}
                            </button>
                        </div>
                    </form>
                )}
            </section>
        </div>
    );
}
