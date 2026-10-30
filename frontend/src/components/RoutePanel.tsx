import type { RouteState } from '../hooks/useRoute';
import { formatDistance, formatGrade } from '../lib/format';
import { isPresetId, PRESETS, type PresetId } from '../lib/presets';
import type { Endpoints } from '../lib/selection';
import type { RouteResponse } from '../lib/routeApi';

// 찍은 위치에서 경로 시작·끝까지 이보다 멀면 안내 문구를 보인다.
const GAP_NOTICE_M = 30;

type RoutePanelProps = {
    preset: PresetId;
    endpoints: Endpoints;
    route: RouteState;
    onPresetChange: (preset: PresetId) => void;
    onReset: () => void;
};

function guide(endpoints: Endpoints): string | null {
    if (!endpoints.start) {
        return '출발지를 검색하거나 지도를 눌러 고르세요.';
    }
    if (!endpoints.goal) {
        return '도착지를 검색하거나 지도를 눌러 고르세요.';
    }
    return null;
}

function gapNotices(route: RouteResponse): string[] {
    const notices = [];
    if (route.start_gap_m >= GAP_NOTICE_M) {
        notices.push(
            `출발지에서 ${formatDistance(route.start_gap_m)} 떨어진 길부터 안내합니다.`,
        );
    }
    if (route.goal_gap_m >= GAP_NOTICE_M) {
        notices.push(
            `도착지 ${formatDistance(route.goal_gap_m)} 앞 길까지 안내합니다.`,
        );
    }
    return notices;
}

function RouteSummary({ route }: { route: RouteResponse }) {
    return (
        <>
            <dl className="route-panel__summary">
                <div>
                    <dt>거리</dt>
                    <dd>{formatDistance(route.distance_m)}</dd>
                </div>
                <div>
                    <dt>최대 경사</dt>
                    <dd>{formatGrade(route.max_grade)}</dd>
                </div>
                <div>
                    <dt>오르막</dt>
                    <dd>{Math.round(route.ascent_m)}m</dd>
                </div>
                <div>
                    <dt>계단</dt>
                    <dd>{route.steps_count}곳</dd>
                </div>
            </dl>
            {gapNotices(route).map((notice) => (
                <p key={notice} className="route-panel__note">
                    {notice}
                </p>
            ))}
        </>
    );
}

export default function RoutePanel({
    preset,
    endpoints,
    route,
    onPresetChange,
    onReset,
}: RoutePanelProps) {
    const message = guide(endpoints);

    return (
        <section className="route-panel" aria-label="경로 찾기">
            <div className="route-panel__row">
                <label className="route-panel__preset">
                    이동 조건
                    <select
                        value={preset}
                        onChange={(event) => {
                            if (isPresetId(event.target.value)) {
                                onPresetChange(event.target.value);
                            }
                        }}
                    >
                        {PRESETS.map((option) => (
                            <option key={option.id} value={option.id}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </label>
                {endpoints.start && (
                    <button
                        type="button"
                        className="route-panel__reset"
                        onClick={onReset}
                    >
                        다시 고르기
                    </button>
                )}
            </div>

            <div aria-live="polite">
                {message && <p className="route-panel__guide">{message}</p>}
                {route.status === 'loading' && (
                    <p className="route-panel__guide">경로를 찾는 중…</p>
                )}
                {route.status === 'error' && (
                    <p role="alert" className="route-panel__error">
                        {route.message}
                    </p>
                )}
                {route.status === 'success' && (
                    <RouteSummary route={route.route} />
                )}
            </div>
        </section>
    );
}
