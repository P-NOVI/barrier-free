import { type SavedPlace, savedPlaceTitle } from '../lib/savedPlacesApi';

type SavedPanelProps = {
    places: SavedPlace[];
    /** false 면 백엔드·DB가 꺼져 저장한 장소를 불러오지 못한 것이다. */
    available: boolean;
    /** 장소 저장·삭제에 실패했을 때 알림 */
    error: string | null;
    onSelect: (place: SavedPlace) => void;
    onDelete: (id: number) => void;
};

/** 저장 탭: 내 장소(집·회사 등)와 즐겨찾기 목록. 누르면 지도에서 그 장소를 보인다. */
export default function SavedPanel({
    places,
    available,
    error,
    onSelect,
    onDelete,
}: SavedPanelProps) {
    if (!available) {
        return (
            <p className="saved-panel__status">
                저장한 장소를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.
            </p>
        );
    }
    return (
        <div className="saved-panel">
            {error && (
                <p role="alert" className="saved-panel__error">
                    {error}
                </p>
            )}
            <PlaceList
                title="내 장소"
                empty="장소 카드의 북마크를 눌러 집·회사를 추가해 보세요."
                places={places.filter((place) => place.kind === 'mine')}
                onSelect={onSelect}
                onDelete={onDelete}
            />
            <PlaceList
                title="즐겨찾기"
                empty="장소 카드의 북마크에서 ☆ 즐겨찾기를 눌러 추가해 보세요."
                places={places.filter((place) => place.kind === 'favorite')}
                onSelect={onSelect}
                onDelete={onDelete}
            />
        </div>
    );
}

type PlaceListProps = {
    title: string;
    empty: string;
    places: SavedPlace[];
    onSelect: (place: SavedPlace) => void;
    onDelete: (id: number) => void;
};

function PlaceList({
    title,
    empty,
    places,
    onSelect,
    onDelete,
}: PlaceListProps) {
    return (
        <section className="saved-panel__group" aria-label={title}>
            <h3 className="saved-panel__title">{title}</h3>
            {places.length === 0 ? (
                <p className="saved-panel__status">{empty}</p>
            ) : (
                <ul className="saved-panel__list">
                    {places.map((place) => (
                        <li key={place.id} className="saved-panel__place">
                            <button
                                type="button"
                                className="saved-panel__pick"
                                onClick={() => onSelect(place)}
                            >
                                <span className="saved-panel__name">
                                    {savedPlaceTitle(place)}
                                </span>
                                <span className="saved-panel__detail">
                                    {place.label
                                        ? place.name
                                        : (place.address ?? '')}
                                </span>
                            </button>
                            <button
                                type="button"
                                className="saved-panel__delete"
                                aria-label={`${savedPlaceTitle(place)} 지우기`}
                                onClick={() => onDelete(place.id)}
                            >
                                ×
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </section>
    );
}
