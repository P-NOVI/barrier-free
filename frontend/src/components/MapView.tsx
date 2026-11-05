import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import type { LocationFix } from '../lib/geolocation';
import {
    type LngLat,
    loadKakaoMaps,
    panToFit,
    SEOUL_CITY_HALL,
    toLatLng,
    toLngLat,
} from '../lib/kakaoMap';
import { arrowsAlong } from '../lib/routeArrows';
import { type SavedPlace, savedPlaceTitle } from '../lib/savedPlacesApi';
import { smoothJogs } from '../lib/routeShape';

// 카카오맵 확대 수준. 숫자가 작을수록 확대 (1~14)
const DEFAULT_LEVEL = 4;
// 안내를 시작할 때 확대 수준. 걸으며 골목이 보이게 기본보다 한 단계 확대한다.
const FOLLOW_LEVEL = 3;

// 경로 선: 진한 테두리 위에 밝은 선을 겹쳐 지도 도로·노선과 구분한다.
const ROUTE_OUTLINE: Omit<kakao.maps.PolylineOptions, 'path'> = {
    strokeWeight: 12,
    strokeColor: '#0d47a1',
    strokeOpacity: 1,
    strokeStyle: 'solid',
    zIndex: 1,
};
const ROUTE_LINE: Omit<kakao.maps.PolylineOptions, 'path'> = {
    strokeWeight: 8,
    strokeColor: '#1a73e8',
    strokeOpacity: 1,
    strokeStyle: 'solid',
    zIndex: 2,
};
// 경로 선 안 진행 방향 화살표 간격(화면 px)
const ROUTE_ARROW_SPACING_PX = 40;
// 찍은 위치와 실제 경로 시작·끝 지점 사이를 잇는 점선
const GAP_LINE: Omit<kakao.maps.PolylineOptions, 'path'> = {
    strokeWeight: 3,
    strokeColor: '#5f6368',
    strokeOpacity: 0.8,
    strokeStyle: 'shortdash',
};
// 내 위치 오차 반경
const ACCURACY_CIRCLE: Omit<kakao.maps.CircleOptions, 'center' | 'radius'> = {
    strokeWeight: 1,
    strokeColor: '#1a73e8',
    strokeOpacity: 0.5,
    fillColor: '#1a73e8',
    fillOpacity: 0.12,
};
// 화살표 < 저장한 장소 별 < 내 위치 점 < 출발·도착 핀 순으로 위에 그린다.
const ROUTE_ARROW_Z_INDEX = 0;
const SAVED_PLACE_Z_INDEX = 1;
const MY_LOCATION_Z_INDEX = 2;
const PIN_Z_INDEX = 3;
// 선택한 장소 카드는 핀 위에 뜬다.
const POPUP_Z_INDEX = 4;
// 카드 아래 꼬리 높이(px). index.css 의 .place-info::after 와 같은 값.
const POPUP_TAIL = 10;
// 핀 크기(px). index.css 의 .map-pin 과 같은 값.
const PIN_WIDTH = 32;
const PIN_HEIGHT = 47;
// 출발·도착 핀: 둥근 머리에 글자를 넣고, 아래 뾰족한 끝이 지점을 가리킨다. 색은 CSS 가 정한다.
const PIN_SVG =
    '<svg viewBox="0 0 24 35" aria-hidden="true">' +
    '<path d="M12 35 1.76 18.26A12 12 0 1 1 22.24 18.26Z"/>' +
    '</svg>';
// 즐겨찾기·내 장소: 동그라미 안 별. 색은 CSS 가 정한다.
const STAR_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<circle cx="12" cy="12" r="12"/>' +
    '<path d="M12 6.2 13.62 10.38 18.09 10.62 14.62 13.45 15.76 17.78 12 15.35 8.24 17.78 9.38 13.45 5.91 10.62 10.38 10.38Z"/>' +
    '</svg>';
// OSMF 출처 가이드라인: 처음에 보인 출처는 5초 뒤 접어도 되고, 접은 뒤에도 찾을 수 있어야 한다.
const ATTRIBUTION_COLLAPSE_MS = 5000;
// 기본값을 렌더마다 새 배열로 만들면 마커 effect 가 매번 다시 돈다
const NO_SAVED_PLACES: SavedPlace[] = [];
/** 경로 전체가 보이게 맞출 때 지도 가장자리 여백(px) */
export type FitPadding = {
    top: number;
    right: number;
    bottom: number;
    left: number;
};

const DEFAULT_FIT_PADDING: FitPadding = {
    top: 48,
    right: 48,
    bottom: 48,
    left: 48,
};

type MapViewProps = {
    center?: LngLat;
    start?: LngLat | null;
    goal?: LngLat | null;
    /** 지도를 눌러 고른 장소. popup 이 있으면 카드가, 없으면 핀이 이 위치를 가리킨다. */
    picked?: LngLat | null;
    /** picked 위치 위에 띄울 카드. 아래 꼬리가 그 위치를 가리킨다. */
    popup?: ReactNode;
    path?: LngLat[] | null;
    /** 경로가 건물 출입구에서 시작·끝나면 그 출입구. 점선이 출입구를 거쳐 간다. */
    startEntrance?: LngLat | null;
    goalEntrance?: LngLat | null;
    /** 별 아이콘으로 보여 줄 즐겨찾기·내 장소 */
    savedPlaces?: SavedPlace[];
    /** 내 위치. 파란 점과 오차 반경 원으로 그린다. */
    myLocation?: LocationFix | null;
    /** 지도 위에 패널이 떠 있으면 그만큼 여백을 더 준다. 바뀌면 경로에 다시 맞춘다. */
    fitPadding?: FitPadding;
    /** 경로가 바뀌면 경로 전체가 보이게 맞출지. 안내 중에는 내 위치를 따라가므로 끈다. */
    fitRoute?: boolean;
    /** 지도 가운데에 계속 둘 위치 (안내 중 내 위치) */
    follow?: LngLat | null;
    onMapClick?: (position: LngLat) => void;
    onSavedPlaceClick?: (place: SavedPlace) => void;
    /** 사용자가 지도를 끌기 시작할 때 */
    onDragStart?: () => void;
    /** 지도 이동·확대가 끝날 때마다 화면 중심을 알린다. */
    onCenterChange?: (center: LngLat) => void;
};

/** 지도 이벤트를 붙이고, 지도나 handler 가 바뀌면 뗀다. */
function useMapEvent(
    map: kakao.maps.Map | null,
    type: 'click' | 'idle' | 'dragstart',
    handler:
        | ((event: kakao.maps.event.MouseEvent) => void)
        | (() => void)
        | undefined,
) {
    useEffect(() => {
        if (!map || !handler) {
            return;
        }
        kakao.maps.event.addListener(map, type, handler);
        return () => kakao.maps.event.removeListener(map, type, handler);
    }, [map, type, handler]);
}

function usePin(
    map: kakao.maps.Map | null,
    position: LngLat | null | undefined,
    label: string,
    modifier: string,
) {
    useEffect(() => {
        if (!map || !position) {
            return;
        }
        const content = document.createElement('div');
        content.className = `map-pin map-pin--${modifier}`;
        content.innerHTML = PIN_SVG;
        const text = document.createElement('span');
        text.className = 'map-pin__label';
        text.textContent = label;
        content.append(text);
        const overlay = new kakao.maps.CustomOverlay({
            position: toLatLng(position),
            content,
            yAnchor: 1,
            zIndex: PIN_Z_INDEX,
        });
        overlay.setMap(map);
        return () => overlay.setMap(null);
    }, [map, position, label, modifier]);
}

/** position 위에 카드를 띄울 자리를 만들고, 그 DOM 을 돌려준다. 카드는 portal 로 그린다. */
function usePopup(
    map: kakao.maps.Map | null,
    position: LngLat | null | undefined,
    inset: FitPadding,
) {
    const [content] = useState(() => {
        const element = document.createElement('div');
        element.className = 'map-popup';
        return element;
    });
    useEffect(() => {
        if (!map || !position) {
            return;
        }
        const overlay = new kakao.maps.CustomOverlay({
            position: toLatLng(position),
            content,
            yAnchor: 1,
            // 카드 안을 눌러도 지도 클릭으로 넘어가지 않게 한다.
            clickable: true,
            zIndex: POPUP_Z_INDEX,
        });
        overlay.setMap(map);

        // 카드 DOM 은 높이 0 인 자리에 아래를 기준으로 붙어 있다(.map-popup).
        // 이름·주소가 와서 카드가 커져도 꼬리 끝이 고른 위치에 그대로 있다.
        const card = content.firstElementChild;
        if (!(card instanceof HTMLElement)) {
            return () => overlay.setMap(null);
        }

        // 카드가 화면 밖이나 패널 뒤로 잘리면 보이도록 지도를 옮긴다.
        // 이름·주소가 오면 카드 크기가 달라지므로 크기가 바뀔 때마다 다시 본다.
        let lastHeight = 0;
        const keepInView = () => {
            const height = card.offsetHeight + POPUP_TAIL;
            // 사용자가 지도를 끌어 카드를 화면 밖으로 보냈을 때 되돌리지 않도록,
            // 카드 높이가 실제로 달라졌을 때만 본다. 숨겨졌다 다시 보이는 것(0)은 무시한다.
            if (height === POPUP_TAIL || height === lastHeight) {
                return;
            }
            lastHeight = height;
            const { x, y } = map
                .getProjection()
                .containerPointFromCoords(toLatLng(position));
            const node = map.getNode();
            const [dx, dy] = panToFit(
                {
                    left: x - card.offsetWidth / 2,
                    right: x + card.offsetWidth / 2,
                    top: y - height,
                    bottom: y,
                },
                { width: node.clientWidth, height: node.clientHeight },
                inset,
            );
            if (dx || dy) {
                map.panBy(dx, dy);
            }
        };
        const observer = new ResizeObserver(keepInView);
        observer.observe(card);
        return () => {
            observer.disconnect();
            overlay.setMap(null);
        };
    }, [map, position, content, inset]);
    return content;
}

/**
 * 핀만 둔 고른 장소(좁은 화면)가 지도 가장자리나 inset 밖에 있으면 보이게 지도를 옮긴다.
 * 아래 시트가 커지거나 줄어 지도 크기가 바뀔 때도 다시 본다.
 */
function useKeepInView(
    map: kakao.maps.Map | null,
    position: LngLat | null | undefined,
    inset: FitPadding,
) {
    useEffect(() => {
        if (!map || !position) {
            return;
        }
        const node = map.getNode();
        const keepInView = () => {
            const { x, y } = map
                .getProjection()
                .containerPointFromCoords(toLatLng(position));
            const [dx, dy] = panToFit(
                {
                    left: x - PIN_WIDTH / 2,
                    right: x + PIN_WIDTH / 2,
                    top: y - PIN_HEIGHT,
                    bottom: y,
                },
                { width: node.clientWidth, height: node.clientHeight },
                inset,
            );
            if (dx || dy) {
                map.panBy(dx, dy);
            }
        };
        // 처음 붙일 때 한 번, 그 뒤로는 지도 크기가 바뀔 때마다 본다.
        const observer = new ResizeObserver(keepInView);
        observer.observe(node);
        return () => observer.disconnect();
    }, [map, position, inset]);
}

/** 즐겨찾기·내 장소마다 별 아이콘을 그린다. 내 장소는 이름(집, 회사 등)을 아래에 붙인다. */
function useSavedPlaceMarkers(
    map: kakao.maps.Map | null,
    places: SavedPlace[],
    onClick: ((place: SavedPlace) => void) | undefined,
) {
    useEffect(() => {
        if (!map) {
            return;
        }
        const overlays = places.map((place) => {
            const content = document.createElement('button');
            content.type = 'button';
            content.className = 'saved-place-pin';
            content.setAttribute(
                'aria-label',
                `${place.kind === 'mine' ? '내 장소' : '즐겨찾기'} ${savedPlaceTitle(place)}`,
            );
            content.innerHTML = STAR_SVG;
            if (place.label) {
                const label = document.createElement('span');
                label.className = 'saved-place-pin__label';
                label.textContent = place.label;
                content.append(label);
            }
            if (onClick) {
                content.addEventListener('click', () => onClick(place));
            }
            // 이름표는 CSS 에서 버튼 밖에 띄우므로 별 가운데가 장소를 가리킨다.
            const overlay = new kakao.maps.CustomOverlay({
                position: toLatLng(place.position),
                content,
                // 눌러도 지도 클릭(출발·도착 고르기)으로 번지지 않게 한다.
                clickable: true,
                zIndex: SAVED_PLACE_Z_INDEX,
            });
            overlay.setMap(map);
            return overlay;
        });
        return () => overlays.forEach((overlay) => overlay.setMap(null));
    }, [map, places, onClick]);
}

/** 경로 데이터의 OpenStreetMap 출처. 5초 뒤 (i) 버튼으로 접히고, 누르면 다시 펼친다. */
function OsmAttribution() {
    const [open, setOpen] = useState(true);
    useEffect(() => {
        const timer = setTimeout(() => setOpen(false), ATTRIBUTION_COLLAPSE_MS);
        return () => clearTimeout(timer);
    }, []);
    return (
        <div className="map-view__attribution">
            {open && (
                <a
                    href="https://www.openstreetmap.org/copyright"
                    target="_blank"
                    rel="noreferrer"
                >
                    © OpenStreetMap
                </a>
            )}
            <button
                type="button"
                className="map-view__attribution-toggle"
                aria-label="지도 데이터 출처"
                aria-expanded={open}
                onClick={() => setOpen((value) => !value)}
            >
                i
            </button>
        </div>
    );
}

function useMyLocation(
    map: kakao.maps.Map | null,
    fix: LocationFix | null | undefined,
) {
    useEffect(() => {
        if (!map || !fix) {
            return;
        }
        const center = toLatLng(fix.position);
        const content = document.createElement('div');
        content.className = 'my-location-dot';
        content.setAttribute('role', 'img');
        content.setAttribute('aria-label', '내 위치');
        const dot = new kakao.maps.CustomOverlay({
            position: center,
            content,
            zIndex: MY_LOCATION_Z_INDEX,
        });
        const circle = new kakao.maps.Circle({
            ...ACCURACY_CIRCLE,
            center,
            radius: fix.accuracy,
        });
        circle.setMap(map);
        dot.setMap(map);
        return () => {
            dot.setMap(null);
            circle.setMap(null);
        };
    }, [map, fix]);
}

function useRouteLine(
    map: kakao.maps.Map | null,
    path: LngLat[] | null | undefined,
    start: LngLat | null | undefined,
    goal: LngLat | null | undefined,
    startEntrance: LngLat | null | undefined,
    goalEntrance: LngLat | null | undefined,
    padding: FitPadding,
    fit: boolean,
) {
    useEffect(() => {
        if (!map || !path || path.length < 2) {
            return;
        }
        const gaps = [
            start && [
                start,
                ...(startEntrance ? [startEntrance] : []),
                path[0],
            ],
            goal && [
                path[path.length - 1],
                ...(goalEntrance ? [goalEntrance] : []),
                goal,
            ],
        ].filter((gap): gap is LngLat[] => Boolean(gap));
        const lines = [
            ...[ROUTE_OUTLINE, ROUTE_LINE].map(
                (style) =>
                    new kakao.maps.Polyline({
                        ...style,
                        path: path.map(toLatLng),
                    }),
            ),
            ...gaps.map(
                (gap) =>
                    new kakao.maps.Polyline({
                        ...GAP_LINE,
                        path: gap.map(toLatLng),
                    }),
            ),
        ];
        lines.forEach((line) => line.setMap(map));

        const removeLines = () => lines.forEach((line) => line.setMap(null));
        if (!fit) {
            return removeLines;
        }
        const bounds = new kakao.maps.LatLngBounds();
        [...path, ...gaps.flat()].forEach((point) =>
            bounds.extend(toLatLng(point)),
        );
        const fitBounds = () => {
            // 시트를 여닫아 지도 크기가 바뀌면 바뀐 크기로 다시 맞춘다.
            map.relayout();
            map.setBounds(
                bounds,
                padding.top,
                padding.right,
                padding.bottom,
                padding.left,
            );
        };
        fitBounds();
        const observer = new ResizeObserver(fitBounds);
        observer.observe(map.getNode());
        return () => {
            observer.disconnect();
            removeLines();
        };
    }, [map, path, start, goal, startEntrance, goalEntrance, padding, fit]);
}

/** position 을 지도 가운데에 계속 둔다. 따라가기를 시작할 때 걷기 좋게 확대한다. */
function useFollow(
    map: kakao.maps.Map | null,
    position: LngLat | null | undefined,
) {
    const following = Boolean(position);
    useEffect(() => {
        if (map && following && map.getLevel() > FOLLOW_LEVEL) {
            map.setLevel(FOLLOW_LEVEL);
        }
    }, [map, following]);
    useEffect(() => {
        if (map && position) {
            map.panTo(toLatLng(position));
        }
    }, [map, position]);
}

/** 경로 선 안에 진행 방향 화살표를 그린다. 확대 수준이 바뀌면 화면 간격에 맞춰 다시 놓는다. */
function useRouteArrows(
    map: kakao.maps.Map | null,
    path: LngLat[] | null | undefined,
) {
    useEffect(() => {
        if (!map || !path || path.length < 2) {
            return;
        }
        let arrows: kakao.maps.CustomOverlay[] = [];
        const clear = () => arrows.forEach((arrow) => arrow.setMap(null));
        const draw = () => {
            clear();
            const projection = map.getProjection();
            const points = path.map((point) =>
                projection.pointFromCoords(toLatLng(point)),
            );
            arrows = arrowsAlong(points, ROUTE_ARROW_SPACING_PX).map(
                ({ x, y, angle }) => {
                    const content = document.createElement('div');
                    content.className = 'route-arrow';
                    content.style.setProperty('--angle', `${angle}deg`);
                    const arrow = new kakao.maps.CustomOverlay({
                        position: projection.coordsFromPoint(
                            new kakao.maps.Point(x, y),
                        ),
                        content,
                        zIndex: ROUTE_ARROW_Z_INDEX,
                    });
                    arrow.setMap(map);
                    return arrow;
                },
            );
        };
        draw();
        kakao.maps.event.addListener(map, 'zoom_changed', draw);
        return () => {
            kakao.maps.event.removeListener(map, 'zoom_changed', draw);
            clear();
        };
    }, [map, path]);
}

export default function MapView({
    center = SEOUL_CITY_HALL,
    start,
    goal,
    picked,
    popup,
    path,
    startEntrance,
    goalEntrance,
    savedPlaces = NO_SAVED_PLACES,
    myLocation,
    fitPadding = DEFAULT_FIT_PADDING,
    fitRoute = true,
    follow,
    onMapClick,
    onSavedPlaceClick,
    onCenterChange,
    onDragStart,
}: MapViewProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const mapRef = useRef<kakao.maps.Map | null>(null);
    const centerRef = useRef(center);
    const [map, setMap] = useState<kakao.maps.Map | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        centerRef.current = center;
        // 화면보다 먼 곳이면 카카오맵이 애니메이션 없이 옮긴다.
        mapRef.current?.panTo(toLatLng(center));
    }, [center]);

    useEffect(() => {
        let cancelled = false;
        loadKakaoMaps()
            .then((maps) => {
                if (cancelled || !containerRef.current || mapRef.current) {
                    return;
                }
                const map = new maps.Map(containerRef.current, {
                    center: toLatLng(centerRef.current),
                    level: DEFAULT_LEVEL,
                });
                mapRef.current = map;
                setMap(map);
            })
            .catch((reason: unknown) => {
                if (!cancelled) {
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : String(reason),
                    );
                }
            });
        return () => {
            cancelled = true;
        };
    }, []);

    const handleClick = useMemo(
        () =>
            onMapClick &&
            ((event: kakao.maps.event.MouseEvent) =>
                onMapClick(toLngLat(event.latLng))),
        [onMapClick],
    );
    const handleIdle = useMemo(() => {
        if (!map || !onCenterChange) {
            return undefined;
        }
        return () => onCenterChange(toLngLat(map.getCenter()));
    }, [map, onCenterChange]);

    useMapEvent(map, 'click', handleClick);
    useMapEvent(map, 'idle', handleIdle);
    useMapEvent(map, 'dragstart', onDragStart);
    useEffect(() => {
        const container = containerRef.current;
        if (!map || !container) {
            return;
        }
        // 화면 배치가 바뀌어 지도 크기가 달라지면 카카오맵에 알려야 지도가 빈칸 없이 그려진다.
        // 시트를 열어 지도가 줄어도 보던 곳이 가운데에 남게 중심을 지킨다.
        const observer = new ResizeObserver(() => {
            const center = map.getCenter();
            map.relayout();
            map.setCenter(center);
        });
        observer.observe(container);
        return () => observer.disconnect();
    }, [map]);

    // 선과 화살표만 다듬은 모양으로 그린다. 안내는 원래 좌표로 계산한다(lib/routeShape.ts).
    const routeShape = useMemo(() => path && smoothJogs(path), [path]);
    useRouteLine(
        map,
        routeShape,
        start,
        goal,
        startEntrance,
        goalEntrance,
        fitPadding,
        fitRoute,
    );
    useFollow(map, follow);
    useRouteArrows(map, routeShape);
    useMyLocation(map, myLocation);
    useSavedPlaceMarkers(map, savedPlaces, onSavedPlaceClick);
    usePin(map, start, '출발', 'start');
    usePin(map, goal, '도착', 'goal');
    // 넓은 화면은 고른 자리 위에 카드를 띄운다. 좁은 화면은 카드를 아래 시트로 보이고 지도에는 핀만 둔다.
    const popupContainer = usePopup(map, popup ? picked : null, fitPadding);
    usePin(map, popup ? null : picked, '', 'picked');
    useKeepInView(map, popup ? null : picked, fitPadding);

    return (
        <div className="map-view">
            <div ref={containerRef} className="map-view__canvas" />
            <OsmAttribution />
            {popup && createPortal(popup, popupContainer)}
            {error && (
                <p role="alert" className="map-view__error">
                    {error}
                </p>
            )}
        </div>
    );
}
