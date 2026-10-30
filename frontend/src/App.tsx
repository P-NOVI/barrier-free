import { useCallback, useState } from 'react';

import MapView from './components/MapView';
import PlaceSearch from './components/PlaceSearch';
import RoutePanel from './components/RoutePanel';
import { useRoute } from './hooks/useRoute';
import { type LngLat, SEOUL_CITY_HALL } from './lib/kakaoMap';
import { DEFAULT_PRESET, type PresetId } from './lib/presets';
import {
    type Endpoint,
    type EndpointRole,
    NO_ENDPOINTS,
    selectEndpoint,
} from './lib/selection';

export default function App() {
    const [preset, setPreset] = useState<PresetId>(DEFAULT_PRESET);
    const [endpoints, setEndpoints] = useState(NO_ENDPOINTS);
    // 검색이나 현재 위치로 마지막에 고른 곳. 지도를 그리로 옮긴다.
    const [focus, setFocus] = useState<LngLat | null>(null);
    const start = endpoints.start?.position ?? null;
    const goal = endpoints.goal?.position ?? null;
    const route = useRoute(start, goal, preset);

    const handleMapClick = useCallback(
        (position: LngLat) =>
            setEndpoints((current) => selectEndpoint(current, position)),
        [],
    );

    const handleSelect = useCallback(
        (role: EndpointRole, endpoint: Endpoint) => {
            setEndpoints((current) => ({ ...current, [role]: endpoint }));
            setFocus(endpoint.position);
        },
        [],
    );

    return (
        <div className="app">
            <MapView
                center={focus ?? undefined}
                start={start}
                goal={goal}
                path={
                    route.status === 'success' ? route.route.coordinates : null
                }
                onMapClick={handleMapClick}
            />
            <PlaceSearch
                endpoints={endpoints}
                near={start ?? goal ?? focus ?? SEOUL_CITY_HALL}
                onSelect={handleSelect}
            />
            <RoutePanel
                preset={preset}
                endpoints={endpoints}
                route={route}
                onPresetChange={setPreset}
                onReset={() => setEndpoints(NO_ENDPOINTS)}
            />
        </div>
    );
}
