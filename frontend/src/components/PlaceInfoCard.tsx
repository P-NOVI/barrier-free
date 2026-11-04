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

export default function PlaceInfoCard({
    place,
    saved = [],
    onSave,
    onUnsave,
    saveError,
    onPick,
    onClose,
}: PlaceInfoCardProps) {
    // 내 장소 이름을 고르는 칸을 펼쳤는지
    const [choosing, setChoosing] = useState(false);
    const [customLabel, setCustomLabel] = useState('');
    const favorite = saved.find((entry) => entry.kind === 'favorite');
    const myLabels = saved
        .filter((entry) => entry.kind === 'mine')
        .map((entry) => entry.label);

    const saveMine = (label: string) => {
        onSave?.('mine', label);
        setChoosing(false);
        setCustomLabel('');
    };

    const handleCustomSubmit = (event: FormEvent) => {
        event.preventDefault();
        const label = customLabel.trim();
        if (label) {
            saveMine(label);
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
                ×
            </button>
            <h2 className="place-info__name">
                {place.name ?? MAP_CLICK_LABEL}
            </h2>
            <p className="place-info__address">
                {place.address ?? '주소를 찾지 못했어요.'}
            </p>
            {onSave && (
                <div className="place-info__save">
                    <button
                        type="button"
                        className="place-info__save-button"
                        aria-pressed={favorite !== undefined}
                        onClick={() =>
                            favorite
                                ? onUnsave?.(favorite.id)
                                : onSave('favorite', null)
                        }
                    >
                        {favorite ? '★' : '☆'} 즐겨찾기
                    </button>
                    <button
                        type="button"
                        className="place-info__save-button"
                        aria-expanded={choosing}
                        onClick={() => setChoosing((open) => !open)}
                    >
                        {myLabels.length > 0
                            ? `내 장소: ${myLabels.join(', ')}`
                            : '내 장소로 저장'}
                    </button>
                </div>
            )}
            {onSave && choosing && (
                <form
                    className="place-info__labels"
                    aria-label="내 장소 이름"
                    onSubmit={handleCustomSubmit}
                >
                    {MY_PLACE_LABELS.map((label) => (
                        <button
                            key={label}
                            type="button"
                            className="place-info__label"
                            onClick={() => saveMine(label)}
                        >
                            {label}
                        </button>
                    ))}
                    <input
                        className="place-info__label-input"
                        aria-label="직접 입력"
                        placeholder="직접 입력"
                        maxLength={LABEL_MAX_LENGTH}
                        value={customLabel}
                        onChange={(event) => setCustomLabel(event.target.value)}
                    />
                    <button
                        type="submit"
                        className="place-info__label"
                        disabled={customLabel.trim() === ''}
                    >
                        저장
                    </button>
                </form>
            )}
            {onSave && saveError && (
                <p role="alert" className="place-info__error">
                    {saveError}
                </p>
            )}
            <div className="place-info__actions">
                <button
                    type="button"
                    className="place-info__action place-info__action--start"
                    onClick={() => onPick('start')}
                >
                    출발
                </button>
                <button
                    type="button"
                    className="place-info__action place-info__action--goal"
                    onClick={() => onPick('goal')}
                >
                    도착
                </button>
            </div>
        </section>
    );
}
