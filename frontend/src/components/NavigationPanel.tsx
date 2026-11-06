import { useState } from 'react';

import type { NavigationState } from '../hooks/useNavigation';
import type { RouteState } from '../hooks/useRoute';
import { formatDistance } from '../lib/format';
import type { GoalGap } from '../lib/navigation';
import type { RouteReport } from '../lib/routeApi';
import { DIRECTION_LABELS, type Turn } from '../lib/turns';
import ReviewPrompt from './ReviewPrompt';

type NavigationPanelProps = {
    route: RouteState;
    navigation: NavigationState;
    /** 지도가 내 위치를 따라가는 중인지 */
    following: boolean;
    /** 음성 안내가 켜져 있는지 */
    voice: boolean;
    /** 없으면(음성 기능이 없는 브라우저) 음성 버튼을 숨긴다. */
    onVoiceChange?: (on: boolean) => void;
    onStop: () => void;
};

type Notice = { text: string; alert: boolean };

const GOAL_GAP_NOTICES: Record<GoalGap, string> = {
    entrance: '건물 출입구 앞입니다. 점선을 따라 목적지까지 가세요.',
    gap: '길 안내가 끝났습니다. 점선을 따라 목적지까지 가세요.',
};

function notice(route: RouteState, navigation: NavigationState): Notice | null {
    const { fix, progress, judgement, goalGap, error } = navigation;
    if (error) {
        return { text: error, alert: true };
    }
    if (route.status === 'loading') {
        return { text: '지금 위치에서 경로를 다시 찾는 중…', alert: false };
    }
    if (route.status === 'error') {
        return { text: route.message, alert: true };
    }
    if (!fix || !progress) {
        return { text: '내 위치를 찾는 중…', alert: false };
    }
    switch (judgement) {
        case 'arrived':
            return { text: '도착했습니다.', alert: false };
        case 'off_route':
            return {
                text: `경로에서 ${formatDistance(progress.offRouteM)} 벗어났습니다.`,
                alert: false,
            };
        case 'uncertain':
            return {
                text: `위치 오차가 커서(${formatDistance(fix.accuracy)}) 경로를 벗어났는지 판단하지 않습니다.`,
                alert: false,
            };
        default:
            return goalGap
                ? { text: GOAL_GAP_NOTICES[goalGap], alert: false }
                : null;
    }
}

/** 지금 경로가 지나는 승인된 제보. 경로를 다시 찾는 동안에는 바로 전 경로의 것 */
function routeReports(route: RouteState): RouteReport[] {
    if (route.status === 'success') {
        return route.route.reports;
    }
    return route.status === 'loading' ? (route.previous?.reports ?? []) : [];
}

/** 다음 회전 방향 화살표. 회전이 더 없으면 도착 깃발 */
function TurnIcon({ turn }: { turn: Turn | null }) {
    if (!turn) {
        return (
            <svg
                className="navigation-panel__icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
            >
                <path d="M6 3h2v18H6zM8 4h10l-2.5 4L18 12H8z" />
            </svg>
        );
    }
    // 위쪽 화살표를 꺾이는 각도만큼 돌린다. 오른쪽이 +
    const angle = Math.max(-180, Math.min(180, turn.angle));
    return (
        <svg
            className="navigation-panel__icon"
            viewBox="0 0 24 24"
            style={{ transform: `rotate(${angle}deg)` }}
            aria-hidden="true"
        >
            <path d="M12 2l8 9h-5v11H9V11H4z" />
        </svg>
    );
}

function instruction({ next, judgement }: NavigationState): string {
    if (!next) {
        return '-';
    }
    if (judgement === 'arrived') {
        return '도착';
    }
    const distance = formatDistance(next.distanceM);
    return next.turn
        ? `${distance} 앞 ${DIRECTION_LABELS[next.turn.direction]}`
        : `${distance} 앞 도착`;
}

/** 안내 중 경로 패널 자리에 다음 회전, 남은 거리, 안내 상태를 보인다. */
export default function NavigationPanel({
    route,
    navigation,
    following,
    voice,
    onVoiceChange,
    onStop,
}: NavigationPanelProps) {
    const message = notice(route, navigation);
    const { progress, next, judgement } = navigation;
    // 도착한 순간의 제보를 붙들어 둔다. 위치 오차로 판정이 흔들려도 입력하던 창이 닫히지 않게.
    const [reviewReports, setReviewReports] = useState<RouteReport[] | null>(
        null,
    );
    if (judgement === 'arrived' && reviewReports === null) {
        const reports = routeReports(route);
        if (reports.length > 0) {
            setReviewReports(reports);
        }
    }

    return (
        <section
            className="route-panel navigation-panel"
            aria-label="경로 안내"
        >
            <div className="route-panel__row">
                <p className="navigation-panel__next">
                    {next && (
                        <TurnIcon
                            turn={judgement === 'arrived' ? null : next.turn}
                        />
                    )}
                    <strong>{instruction(navigation)}</strong>
                </p>
                <button
                    type="button"
                    className="navigation-panel__stop"
                    onClick={onStop}
                >
                    안내 종료
                </button>
            </div>
            <div className="route-panel__row">
                <p className="navigation-panel__remaining">
                    남은 거리{' '}
                    <strong>
                        {progress ? formatDistance(progress.remainingM) : '-'}
                    </strong>
                </p>
                {onVoiceChange && (
                    <button
                        type="button"
                        className="navigation-panel__voice"
                        aria-pressed={voice}
                        onClick={() => onVoiceChange(!voice)}
                    >
                        {voice ? '음성 안내 켬' : '음성 안내 끔'}
                    </button>
                )}
            </div>
            <div aria-live="polite">
                {message && (
                    <p
                        role={message.alert ? 'alert' : undefined}
                        className={
                            message.alert
                                ? 'route-panel__error'
                                : 'route-panel__guide'
                        }
                    >
                        {message.text}
                    </p>
                )}
            </div>
            {!following && (
                <p className="route-panel__note">
                    지도를 움직여 따라가기를 멈췄습니다. 내 위치 버튼을 누르면
                    다시 따라갑니다.
                </p>
            )}
            {reviewReports && (
                <ReviewPrompt reports={reviewReports} onClose={onStop} />
            )}
        </section>
    );
}
