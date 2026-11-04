import type { RouteState } from '../hooks/useRoute';
import { formatDistance, formatDuration, formatGrade } from '../lib/format';
import { isPresetId, PRESETS, type PresetId } from '../lib/presets';
import type { Endpoints } from '../lib/selection';
import type { RouteResponse } from '../lib/routeApi';

// 찍은 위치에서 경로 시작·끝까지 이보다 멀면 안내 문구를 보인다.
const GAP_NOTICE_M = 30;

type RoutePanelProps = {
    preset: PresetId;
    endpoints: Endpoints;
    /** 안내 문구 아래 작은 글씨 (예: 역 엘리베이터로 바꾼 출발·도착) */
    notes?: string[];
    route: RouteState;
    /** 지금 경로를 내 경로에 저장했는지 */
    saved?: boolean;
    /** 없으면 저장 버튼을 숨긴다(백엔드·DB가 꺼짐). */
    onToggleSave?: () => void;
    /** 내 경로 저장·삭제에 실패했을 때 알림 */
    saveError?: string | null;
    onPresetChange: (preset: PresetId) => void;
    onReset: () => void;
    onStartNavigation: () => void;
};

function guide(endpoints: Endpoints): string | null {
    if (!endpoints.start) {
        return '출발지를 검색하거나, 지도를 눌러 나온 카드에서 고르세요.';
    }
    if (!endpoints.goal) {
        return '도착지를 검색하거나, 지도를 눌러 나온 카드에서 고르세요.';
    }
    return null;
}

function gapNotices(route: RouteResponse): string[] {
    const notices = [];
    if (route.start_entrance) {
        notices.push('출발지 건물 출입구 앞 길부터 안내합니다.');
    } else if (route.start_gap_m >= GAP_NOTICE_M) {
        notices.push(
            `출발지에서 ${formatDistance(route.start_gap_m)} 떨어진 길부터 안내합니다.`,
        );
    }
    if (route.goal_entrance) {
        notices.push('도착지 건물 출입구 앞 길까지 안내합니다.');
    } else if (route.goal_gap_m >= GAP_NOTICE_M) {
        notices.push(
            `도착지 ${formatDistance(route.goal_gap_m)} 앞 길까지 안내합니다.`,
        );
    }
    return notices;
}

// 내 경로 저장 별
const STAR_ICON =
    'M12 4l2.4 5 5.4.6-4 3.7 1.1 5.3L12 16l-4.9 2.6 1.1-5.3-4-3.7 5.4-.6Z';

function RouteSummary({
    route,
    saved,
    onToggleSave,
}: {
    route: RouteResponse;
    saved: boolean;
    onToggleSave?: () => void;
}) {
    return (
        <>
            <div className="route-panel__headline">
                <span className="route-panel__duration">
                    {formatDuration(route.duration_s)}
                </span>
                <span className="route-panel__distance">
                    {formatDistance(route.distance_m)}
                </span>
                {onToggleSave && (
                    <button
                        type="button"
                        className="route-panel__save"
                        aria-label="내 경로에 저장"
                        aria-pressed={saved}
                        onClick={onToggleSave}
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d={STAR_ICON} />
                        </svg>
                    </button>
                )}
            </div>
            <dl className="route-panel__summary">
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
    notes = [],
    route,
    saved = false,
    onToggleSave,
    saveError = null,
    onPresetChange,
    onReset,
    onStartNavigation,
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
                {notes.map((note) => (
                    <p key={note} className="route-panel__note">
                        {note}
                    </p>
                ))}
                {route.status === 'loading' && (
                    <p className="route-panel__guide">경로를 찾는 중…</p>
                )}
                {route.status === 'error' && (
                    <p role="alert" className="route-panel__error">
                        {route.message}
                    </p>
                )}
                {route.status === 'success' && (
                    <RouteSummary
                        route={route.route}
                        saved={saved}
                        onToggleSave={onToggleSave}
                    />
                )}
                {saveError && (
                    <p role="alert" className="route-panel__error">
                        {saveError}
                    </p>
                )}
            </div>
            {route.status === 'success' && (
                <button
                    type="button"
                    className="route-panel__start"
                    onClick={onStartNavigation}
                >
                    안내 시작
                </button>
            )}
        </section>
    );
}
