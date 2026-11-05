import { type FormEvent, useState } from 'react';

import {
    LABEL_MAX_LENGTH,
    MY_PLACE_LABELS,
    type SavedPlace,
    type SavedPlaceKind,
} from '../lib/savedPlacesApi';
import {
    type EndpointRole,
    MAP_CLICK_LABEL,
    type PickedPlace,
} from '../lib/selection';

type PlaceInfoCardProps = {
    place: PickedPlace;
    /** popup: 넓은 화면에서 고른 자리 위에 뜨는 말풍선. sheet: 좁은 화면 아래에 붙는 시트 */
    variant?: 'popup' | 'sheet';
    /** 주소 아래 작은 글씨 (예: 역 엘리베이터 출구) */
    note?: string | null;
    /** 이 위치에 저장한 즐겨찾기·내 장소 */
    saved?: SavedPlace[];
    /** 없으면(백엔드·DB가 꺼짐) 저장 버튼을 숨긴다. */
    onSave?: (kind: SavedPlaceKind, label: string | null) => void;
    onUnsave?: (id: number) => void;
    /** 저장·삭제에 실패했을 때 알림 */
    saveError?: string | null;
    onPick: (role: EndpointRole) => void;
    onClose: () => void;
};

/** 버튼을 눌러 펼친 칸. 한 번에 하나만 펼친다. */
type Panel = 'save' | 'route' | null;

const CLOSE_ICON = (
    <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 5l14 14M19 5 5 19" />
    </svg>
);

/** 즐겨찾기와 내 장소(집·회사·직접 입력한 이름)를 켜고 끄는 칸 */
function SavePanel({
    saved,
    onSave,
    onUnsave,
}: {
    saved: SavedPlace[];
    onSave: (kind: SavedPlaceKind, label: string | null) => void;
    onUnsave?: (id: number) => void;
}) {
    const [customLabel, setCustomLabel] = useState('');
    const favorite = saved.find((entry) => entry.kind === 'favorite');
    const mine = saved.filter((entry) => entry.kind === 'mine');
    // 고르는 칸에는 집·회사와 직접 입력해 저장한 이름을 함께 보인다.
    const labels = [
        ...MY_PLACE_LABELS,
        ...mine
            .map((entry) => entry.label)
            .filter(
                (label): label is string =>
                    label !== null && !MY_PLACE_LABELS.includes(label),
            ),
    ];

    const toggleLabel = (label: string) => {
        const entry = mine.find((candidate) => candidate.label === label);
        if (entry) {
            onUnsave?.(entry.id);
        } else {
            onSave('mine', label);
        }
    };

    const handleCustomSubmit = (event: FormEvent) => {
        event.preventDefault();
        const label = customLabel.trim();
        if (label) {
            onSave('mine', label);
            setCustomLabel('');
        }
    };

    return (
        <div className="place-info__panel">
            <button
                type="button"
                className="place-info__chip"
                aria-pressed={favorite !== undefined}
                onClick={() =>
                    favorite
                        ? onUnsave?.(favorite.id)
                        : onSave('favorite', null)
                }
            >
                {favorite ? '★' : '☆'} 즐겨찾기
            </button>
            <p className="place-info__panel-title">내 장소</p>
            <div className="place-info__chips">
                {labels.map((label) => (
                    <button
                        key={label}
                        type="button"
                        className="place-info__chip"
                        aria-pressed={mine.some(
                            (entry) => entry.label === label,
                        )}
                        onClick={() => toggleLabel(label)}
                    >
                        {label}
                    </button>
                ))}
            </div>
            <form
                className="place-info__custom"
                aria-label="내 장소 이름 직접 입력"
                onSubmit={handleCustomSubmit}
            >
                <input
                    className="place-info__custom-input"
                    aria-label="직접 입력"
                    placeholder="직접 입력 (예: 학교)"
                    maxLength={LABEL_MAX_LENGTH}
                    value={customLabel}
                    onChange={(event) => setCustomLabel(event.target.value)}
                />
                <button
                    type="submit"
                    className="place-info__chip"
                    disabled={customLabel.trim() === ''}
                >
                    저장
                </button>
            </form>
        </div>
    );
}

export default function PlaceInfoCard({
    place,
    variant = 'popup',
    note,
    saved = [],
    onSave,
    onUnsave,
    saveError,
    onPick,
    onClose,
}: PlaceInfoCardProps) {
    const [panel, setPanel] = useState<Panel>(null);
    const isSaved = saved.length > 0;
    const saveLabel = isSaved
        ? '저장한 장소 (즐겨찾기·내 장소 바꾸기)'
        : '즐겨찾기·내 장소로 저장';
    // 분류는 검색으로 고른 장소만 있다.
    const detail = [place.category, place.address ?? '주소를 찾지 못했어요.']
        .filter(Boolean)
        .join(' · ');

    const toggle = (next: Exclude<Panel, null>) =>
        setPanel((current) => (current === next ? null : next));

    const text = (
        <>
            <h2 className="place-info__name">
                {place.name ?? MAP_CLICK_LABEL}
            </h2>
            <p className="place-info__address">{detail}</p>
            {note && <p className="place-info__note">{note}</p>}
        </>
    );
    const error = saveError && (
        <p role="alert" className="place-info__error">
            {saveError}
        </p>
    );
    const savePanel = onSave && panel === 'save' && (
        <SavePanel saved={saved} onSave={onSave} onUnsave={onUnsave} />
    );

    if (variant === 'sheet') {
        return (
            <section className="place-info-sheet" aria-label="선택한 장소">
                <div className="place-info-sheet__head">
                    <div className="place-info-sheet__text">{text}</div>
                    {onSave && (
                        <button
                            type="button"
                            className="place-info-sheet__round place-info-sheet__star"
                            aria-label={saveLabel}
                            aria-expanded={panel === 'save'}
                            data-saved={isSaved || undefined}
                            onClick={() => toggle('save')}
                        >
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M12 3.2l2.7 5.5 6 .9-4.35 4.25 1.03 6L12 17l-5.38 2.85 1.03-6L3.3 9.6l6-.9Z" />
                            </svg>
                        </button>
                    )}
                    <button
                        type="button"
                        className="place-info-sheet__round"
                        aria-label="닫기"
                        onClick={onClose}
                    >
                        {CLOSE_ICON}
                    </button>
                </div>
                {error}
                {savePanel}
                <div className="place-info-sheet__actions">
                    <button
                        type="button"
                        className="place-info-sheet__action place-info-sheet__action--start"
                        onClick={() => onPick('start')}
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M20.5 3.5 3.5 10.6l7.1 2.8 2.8 7.1Z" />
                        </svg>
                        출발
                    </button>
                    <button
                        type="button"
                        className="place-info-sheet__action place-info-sheet__action--goal"
                        onClick={() => onPick('goal')}
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path
                                fillRule="evenodd"
                                d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7Zm0 4.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5Z"
                            />
                        </svg>
                        도착
                    </button>
                </div>
            </section>
        );
    }

    return (
        <section className="place-info" aria-label="선택한 장소">
            <button
                type="button"
                className="place-info__close"
                aria-label="닫기"
                onClick={onClose}
            >
                {CLOSE_ICON}
            </button>
            {text}
            {error}
            <div className="place-info__toolbar">
                {onSave && (
                    <button
                        type="button"
                        className="place-info__bookmark"
                        aria-label={saveLabel}
                        aria-expanded={panel === 'save'}
                        data-saved={isSaved || undefined}
                        onClick={() => toggle('save')}
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M6.5 3.5h11a1 1 0 0 1 1 1v16l-6.5-4.5-6.5 4.5v-16a1 1 0 0 1 1-1Z" />
                        </svg>
                    </button>
                )}
                <button
                    type="button"
                    className="place-info__route"
                    aria-expanded={panel === 'route'}
                    onClick={() => toggle('route')}
                >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M6 21v-7a4 4 0 0 1 4-4h8M14 6l4 4-4 4" />
                    </svg>
                    길찾기
                </button>
            </div>
            {savePanel}
            {panel === 'route' && (
                <div className="place-info__panel">
                    <button
                        type="button"
                        className="place-info__endpoint place-info__endpoint--start"
                        onClick={() => onPick('start')}
                    >
                        출발
                    </button>
                    <button
                        type="button"
                        className="place-info__endpoint place-info__endpoint--goal"
                        onClick={() => onPick('goal')}
                    >
                        도착
                    </button>
                </div>
            )}
        </section>
    );
}
