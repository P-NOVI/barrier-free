import { useCallback, useState } from 'react';

import MapView from './components/MapView';
import RoutePanel from './components/RoutePanel';
import { useRoute } from './hooks/useRoute';
import type { LngLat } from './lib/kakaoMap';
import { DEFAULT_PRESET, type PresetId } from './lib/presets';
import { NO_ENDPOINTS, selectEndpoint } from './lib/selection';

export default function App() {
    const [preset, setPreset] = useState<PresetId>(DEFAULT_PRESET);
    const [endpoints, setEndpoints] = useState(NO_ENDPOINTS);
    const route = useRoute(endpoints.start, endpoints.goal, preset);

    const handleMapClick = useCallback(
        (position: LngLat) =>
            setEndpoints((current) => selectEndpoint(current, position)),
        [],
    );

    return (
        <div className="app">
            <MapView
                start={endpoints.start}
                goal={endpoints.goal}
                path={
                    route.status === 'success' ? route.route.coordinates : null
                }
                onMapClick={handleMapClick}
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
