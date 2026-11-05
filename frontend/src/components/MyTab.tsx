import { type ReactNode, useId, useState } from 'react';

import type { MyReports as MyReportsState } from '../hooks/useMyReports';
import type { SavedPlaces } from '../hooks/useSavedPlaces';
import type { SavedRoutes } from '../hooks/useSavedRoutes';
import { formatDistance } from '../lib/format';
import type { LngLat } from '../lib/kakaoMap';
import { presetLabel } from '../lib/presets';
import type { SavedPlace } from '../lib/savedPlacesApi';
import type { SavedRoute } from '../lib/savedRoutesApi';
import { MY_LIST_ICONS as ICONS } from '../lib/myListIcons';
import MyListRow from './MyListRow';
import MyPlaces from './MyPlaces';
import MyReports from './MyReports';

type Section = 'favorite' | 'mine' | 'routes' | 'reports';

const SECTIONS: { id: Section; label: string }[] = [
    { id: 'favorite', label: '즐겨찾기' },
    { id: 'mine', label: '내 장소' },
    { id: 'routes', label: '내 경로' },
    { id: 'reports', label: '내 제보' },
];
const UNAVAILABLE = '불러오지 못했어요. 잠시 뒤 다시 열어 주세요.';

type MyTabProps = {
    savedPlaces: SavedPlaces;
    savedRoutes: SavedRoutes;
    myReports: MyReportsState;
    /** 내 장소를 등록할 때 이 근처 장소를 앞에 둔다. */
    near: LngLat;
    onSelectPlace: (place: SavedPlace) => void;
    /** 내 경로를 고르면 그 출발·도착과 이동 조건으로 다시 찾는다. */
    onSelectRoute: (route: SavedRoute) => void;
    /** 목록 아래에 덧붙일 내용 (좁은 화면의 로그인·로그아웃) */
    children?: ReactNode;
};

/** My 탭: 즐겨찾기, 내 장소, 내 경로, 내 제보 */
export default function MyTab({
    savedPlaces,
    savedRoutes,
    myReports,
    near,
    onSelectPlace,
    onSelectRoute,
    children,
}: MyTabProps) {
    const [section, setSection] = useState<Section>('favorite');
    const id = useId();
    const source =
        section === 'routes'
            ? savedRoutes
            : section === 'reports'
              ? myReports
              : savedPlaces;
    const { error, available } = source;

    return (
        <div className="my-tab">
            <div role="tablist" className="my-tab__tabs" aria-label="My">
                {SECTIONS.map((item) => (
                    <button
                        key={item.id}
                        type="button"
                        role="tab"
                        id={`${id}-${item.id}`}
                        className="my-tab__tab"
                        aria-selected={item.id === section}
                        aria-controls={`${id}-panel`}
                        onClick={() => setSection(item.id)}
                    >
                        {item.label}
                    </button>
                ))}
            </div>
            <div
                role="tabpanel"
                id={`${id}-panel`}
                className="my-tab__panel"
                aria-labelledby={`${id}-${section}`}
            >
                {error && (
                    <p role="alert" className="my-tab__error">
                        {error}
                    </p>
                )}
                {!available && <p className="my-tab__status">{UNAVAILABLE}</p>}
                {available && section === 'favorite' && (
                    <FavoriteList
                        places={savedPlaces.places.filter(
                            (place) => place.kind === 'favorite',
                        )}
                        onSelect={onSelectPlace}
                        onDelete={savedPlaces.remove}
                    />
                )}
                {available && section === 'mine' && (
                    <MyPlaces
                        places={savedPlaces.places.filter(
                            (place) => place.kind === 'mine',
                        )}
                        near={near}
                        onSelect={onSelectPlace}
                        onDelete={savedPlaces.remove}
                        onAdd={savedPlaces.add}
                    />
                )}
                {available && section === 'routes' && (
                    <SavedRouteList
                        routes={savedRoutes.routes}
                        onSelect={onSelectRoute}
                        onDelete={savedRoutes.remove}
                    />
                )}
                {available && section === 'reports' && (
                    <MyReports
                        reports={myReports.reports}
                        onUpdate={myReports.update}
                        onDelete={myReports.remove}
                    />
                )}
            </div>
            {children}
        </div>
    );
}

// 빈 목록 안내 문장 안의 별
function StarIcon() {
    return (
        <svg className="inline-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d={ICONS.star} />
        </svg>
    );
}

function FavoriteList({
    places,
    onSelect,
    onDelete,
}: {
    places: SavedPlace[];
    onSelect: (place: SavedPlace) => void;
    onDelete: (id: number) => void;
}) {
    if (places.length === 0) {
        return (
            <p className="my-tab__status">
                장소 카드의 북마크에서 <StarIcon /> 즐겨찾기를 눌러 추가해
                보세요.
            </p>
        );
    }
    return (
        <ul className="my-list">
            {places.map((place) => (
                <MyListRow
                    key={place.id}
                    icon={ICONS.star}
                    title={place.name}
                    detail={place.address ?? ''}
                    onPick={() => onSelect(place)}
                    onDelete={() => onDelete(place.id)}
                />
            ))}
        </ul>
    );
}

function SavedRouteList({
    routes,
    onSelect,
    onDelete,
}: {
    routes: SavedRoute[];
    onSelect: (route: SavedRoute) => void;
    onDelete: (id: number) => void;
}) {
    if (routes.length === 0) {
        return (
            <p className="my-tab__status">
                길찾기에서 경로를 찾은 뒤 <StarIcon /> 를 눌러 저장해 보세요.
            </p>
        );
    }
    return (
        <ul className="my-list">
            {routes.map((route) => (
                <MyListRow
                    key={route.id}
                    icon={ICONS.route}
                    title={`${route.start_name} → ${route.goal_name}`}
                    detail={`${presetLabel(route.preset)} · ${formatDistance(route.distance_m)}`}
                    onPick={() => onSelect(route)}
                    onDelete={() => onDelete(route.id)}
                />
            ))}
        </ul>
    );
}
