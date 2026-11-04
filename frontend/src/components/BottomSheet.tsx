import {
    type CSSProperties,
    type PointerEvent,
    type ReactNode,
    useRef,
    useState,
} from 'react';

import {
    clampDrag,
    type SheetSnap,
    snapAfterDrag,
    toggleSnap,
} from '../lib/sheet';

type BottomSheetProps = {
    title: string;
    snap: SheetSnap;
    onSnapChange: (snap: SheetSnap) => void;
    children: ReactNode;
};

/**
 * 화면 아래에서 절반까지 올라오는 시트. 손잡이를 끌거나 누르면 제목만 보이게 접히고,
 * 다시 올리면 절반으로 펼친다.
 */
export default function BottomSheet({
    title,
    snap,
    onSnapChange,
    children,
}: BottomSheetProps) {
    const sheetRef = useRef<HTMLElement>(null);
    // 끌기 시작한 화면 y와 지금까지 끈 거리
    const drag = useRef<{ startY: number; range: number } | null>(null);
    const [dy, setDy] = useState<number | null>(null);

    const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
        const sheet = sheetRef.current;
        if (!sheet) {
            return;
        }
        event.currentTarget.setPointerCapture(event.pointerId);
        // 접힌 시트와 펼친 시트의 높이 차이만큼 끌 수 있다.
        const header = event.currentTarget.offsetHeight;
        drag.current = {
            startY: event.clientY,
            range: Math.max(sheet.offsetHeight - header, 0),
        };
        setDy(0);
    };

    const handlePointerMove = (event: PointerEvent<HTMLButtonElement>) => {
        if (drag.current) {
            setDy(
                clampDrag(
                    snap,
                    event.clientY - drag.current.startY,
                    drag.current.range,
                ),
            );
        }
    };

    const handlePointerUp = () => {
        if (drag.current && dy !== null) {
            onSnapChange(snapAfterDrag(snap, dy));
        }
        drag.current = null;
        setDy(null);
    };

    return (
        <section
            ref={sheetRef}
            className="bottom-sheet"
            aria-label={title}
            data-snap={snap}
            data-dragging={dy !== null || undefined}
            style={{ '--drag': `${dy ?? 0}px` } as CSSProperties}
        >
            <button
                type="button"
                className="bottom-sheet__header"
                aria-expanded={snap === 'half'}
                aria-label={`${title} ${snap === 'half' ? '접기' : '펼치기'}`}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
                // 끌기는 포인터 이벤트로 처리하고, 키보드로 누르면 단계를 바꾼다.
                onClick={(event) => {
                    if (event.detail === 0) {
                        onSnapChange(toggleSnap(snap));
                    }
                }}
            >
                <span className="bottom-sheet__handle" aria-hidden="true" />
                <span className="bottom-sheet__title">{title}</span>
            </button>
            <div className="bottom-sheet__body">{children}</div>
        </section>
    );
}
