import type { NavigationState } from '../hooks/useNavigation';
import type { RouteState } from '../hooks/useRoute';
import { formatDistance } from '../lib/format';

type NavigationPanelProps = {
    route: RouteState;
    navigation: NavigationState;
    /** 지도가 내 위치를 따라가는 중인지 */
    following: boolean;
    onStop: () => void;
};

type Notice = { text: string; alert: boolean };

function notice(route: RouteState, navigation: NavigationState): Notice | null {
    const { fix, progress, judgement, error } = navigation;
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
            return null;
    }
}

/** 안내 중 경로 패널 자리에 남은 거리와 안내 상태를 보인다. */
export default function NavigationPanel({
    route,
    navigation,
    following,
    onStop,
}: NavigationPanelProps) {
    const message = notice(route, navigation);
    const { progress } = navigation;

    return (
        <section
            className="route-panel navigation-panel"
            aria-label="경로 안내"
        >
            <div className="route-panel__row">
                <p className="navigation-panel__remaining">
                    남은 거리
                    <strong>
                        {progress ? formatDistance(progress.remainingM) : '-'}
                    </strong>
                </p>
                <button
                    type="button"
                    className="navigation-panel__stop"
                    onClick={onStop}
                >
                    안내 종료
                </button>
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
        </section>
    );
}
