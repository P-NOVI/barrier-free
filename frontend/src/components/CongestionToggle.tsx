import type { CongestionState } from '../hooks/useCongestion';

type CongestionToggleProps = {
    enabled: boolean;
    state: CongestionState;
    onChange: (enabled: boolean) => void;
};

/** 지도 위 '혼잡도' 온/오프 버튼. 불러오는 중이거나 실패하면 버튼 옆에 알린다. */
export default function CongestionToggle({
    enabled,
    state,
    onChange,
}: CongestionToggleProps) {
    return (
        <div className="congestion-toggle">
            {state.status === 'error' && (
                <p role="alert" className="congestion-toggle__message">
                    {state.message}
                </p>
            )}
            {state.status === 'loading' && (
                <p role="status" className="congestion-toggle__message">
                    혼잡도 불러오는 중
                </p>
            )}
            <button
                type="button"
                className="congestion-toggle__button"
                aria-pressed={enabled}
                title="실시간 혼잡도(S-DoT 유동인구) 보기"
                onClick={() => onChange(!enabled)}
            >
                혼잡도 {enabled ? '켜짐' : '꺼짐'}
            </button>
        </div>
    );
}
