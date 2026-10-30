import {
    type EndpointRole,
    MAP_CLICK_LABEL,
    type PickedPlace,
} from '../lib/selection';

type PlaceInfoCardProps = {
    place: PickedPlace;
    onPick: (role: EndpointRole) => void;
    onClose: () => void;
};

export default function PlaceInfoCard({
    place,
    onPick,
    onClose,
}: PlaceInfoCardProps) {
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
