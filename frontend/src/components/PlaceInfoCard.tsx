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

/** 아래 줄 버튼을 눌러 펼친 칸. 한 번에 하나만 펼친다. */
type Panel = 'save' | 'route' | null;

export default function PlaceInfoCard({
    place,
    note,
    saved = [],
    onSave,
    onUnsave,
    saveError,
    onPick,
    onClose,
}: PlaceInfoCardProps) {
    const [panel, setPanel] = useState<Panel>(null);
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

    const toggle = (next: Exclude<Panel, null>) =>
        setPanel((current) => (current === next ? null : next));

    const toggleLabel = (label: string) => {
        const entry = mine.find((candidate) => candidate.label === label);
        if (entry) {
            onUnsave?.(entry.id);
        } else {
            onSave?.('mine', label);
        }
    };

    const handleCustomSubmit = (event: FormEvent) => {
        event.preventDefault();
        const label = customLabel.trim();
        if (label) {
            onSave?.('mine', label);
            setCustomLabel('');
        }
    };

    return (
        <section className="place-info" aria-label="선택한 장소">
            <button
                type="button"
                className="place-info__close"
                aria-label="닫기"
                onClick={onClose}
            >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M5 5l14 14M19 5 5 19" />
                </svg>
            </button>
            <h2 className="place-info__name">
                {place.name ?? MAP_CLICK_LABEL}
            </h2>
            <p className="place-info__address">
                {place.address ?? '주소를 찾지 못했어요.'}
            </p>
            {note && <p className="place-info__note">{note}</p>}
            {saveError && (
                <p role="alert" className="place-info__error">
                    {saveError}
                </p>
            )}
            <div className="place-info__toolbar">
                {onSave && (
                    <button
                        type="button"
                        className="place-info__bookmark"
                        aria-label={
                            saved.length > 0
                                ? '저장한 장소 (즐겨찾기·내 장소 바꾸기)'
                                : '즐겨찾기·내 장소로 저장'
                        }
                        aria-expanded={panel === 'save'}
                        data-saved={saved.length > 0 || undefined}
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
            {onSave && panel === 'save' && (
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
                            onChange={(event) =>
                                setCustomLabel(event.target.value)
                            }
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
            )}
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
