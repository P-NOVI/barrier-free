import {
    type PointerEvent,
    type ReactNode,
    type RefObject,
    useCallback,
    useEffect,
    useLayoutEffect,
    useRef,
    useState,
} from 'react';

import {
    dragHeight,
    type SheetSnap,
    type SnapHeights,
    snapAfterRelease,
    TAP_SLOP_PX,
    toggleSnap,
} from '../lib/sheet';

type BottomSheetProps = {
    title: string;
    snap: SheetSnap;
    onSnapChange: (snap: SheetSnap) => void;
    children: ReactNode;
};

type Drag = {
    startY: number;
    startHeight: number;
    height: number;
    moved: boolean;
    // 놓을 때 속도를 구할 최근 위치들
    samples: { y: number; t: number }[];
};

// 놓기 직전 이 시간(ms) 동안 움직인 거리로 속도를 구한다.
const VELOCITY_WINDOW_MS = 100;

/** 단계마다 보이는 높이. 시트 크기나 화면 크기가 바뀌면 다시 잰다. */
function useSnapHeights(
    sheetRef: RefObject<HTMLElement | null>,
    headerRef: RefObject<HTMLElement | null>,
): SnapHeights | null {
    const [heights, setHeights] = useState<SnapHeights | null>(null);
    useLayoutEffect(() => {
        const sheet = sheetRef.current;
        const header = headerRef.current;
        const area = sheet?.parentElement;
        if (!sheet || !header || !area) {
            return;
        }
        const measure = () => {
            // 시트 아래쪽 여백은 떠 있는 메뉴 자리다(index.css).
            const menu = parseFloat(getComputedStyle(sheet).paddingBottom) || 0;
            const full = sheet.offsetHeight;
            const collapsed = Math.min(header.offsetHeight + menu, full);
            const half = Math.min(
                Math.max(area.clientHeight / 2, collapsed),
                full,
            );
            setHeights({ collapsed, half, full });
        };
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(area);
        observer.observe(sheet);
        return () => observer.disconnect();
    }, [sheetRef, headerRef]);
    return heights;
}

/**
 * 화면 아래에서 올라오는 시트. 접기·절반·전체 세 단계로 멈춘다.
 * 손잡이나 내용을 끌면 손가락을 바로 따라오고, 놓으면 속도를 보고 가까운 단계로 간다.
 */
export default function BottomSheet({
    title,
    snap,
    onSnapChange,
    children,
}: BottomSheetProps) {
    const sheetRef = useRef<HTMLElement>(null);
    const headerRef = useRef<HTMLButtonElement>(null);
    const bodyRef = useRef<HTMLDivElement>(null);
    const heights = useSnapHeights(sheetRef, headerRef);
    const drag = useRef<Drag | null>(null);
    const [dragging, setDragging] = useState(false);

    const place = useCallback(
        (height: number) => {
            const sheet = sheetRef.current;
            if (sheet && heights) {
                sheet.style.transform = `translateY(${heights.full - height}px)`;
            }
        },
        [heights],
    );

    // 끄는 중이 아니면 단계 자리에 둔다. 같은 단계로 돌아와도 끈 자리에서 되돌린다.
    useLayoutEffect(() => {
        if (!dragging && heights) {
            place(heights[snap]);
        }
    }, [dragging, heights, snap, place]);

    const begin = useCallback(
        (y: number) => {
            if (!heights) {
                return;
            }
            drag.current = {
                startY: y,
                startHeight: heights[snap],
                height: heights[snap],
                moved: false,
                samples: [{ y, t: performance.now() }],
            };
        },
        [heights, snap],
    );

    const move = useCallback(
        (y: number) => {
            const current = drag.current;
            if (!current || !heights) {
                return;
            }
            const dy = y - current.startY;
            if (!current.moved && Math.abs(dy) < TAP_SLOP_PX) {
                return;
            }
            if (!current.moved) {
                current.moved = true;
                setDragging(true);
            }
            const now = performance.now();
            current.samples.push({ y, t: now });
            while (current.samples[0].t < now - VELOCITY_WINDOW_MS) {
                current.samples.shift();
            }
            current.height = dragHeight(current.startHeight, dy, heights);
            place(current.height);
        },
        [heights, place],
    );

    /** 손을 뗐다. 끌지 않고 눌렀으면 tapped 를 부른다. */
    const end = useCallback(
        (tapped?: () => void) => {
            const current = drag.current;
            drag.current = null;
            if (!current || !heights) {
                return;
            }
            if (!current.moved) {
                tapped?.();
                return;
            }
            const first = current.samples[0];
            const last = current.samples[current.samples.length - 1];
            const elapsed = last.t - first.t;
            const velocity = elapsed > 0 ? (first.y - last.y) / elapsed : 0;
            onSnapChange(snapAfterRelease(current.height, velocity, heights));
            setDragging(false);
        },
        [heights, onSnapChange],
    );

    // 내용에서 끌기(터치). 전체가 아닐 때 위로, 내용이 맨 위일 때 아래로 끌면 시트가 움직이고,
    // 그 밖에는 내용이 스크롤된다. 스크롤을 막아야 해서 passive 가 아닌 리스너를 쓴다.
    const latest = useRef({ snap, begin, move, end });
    useLayoutEffect(() => {
        latest.current = { snap, begin, move, end };
    });
    useEffect(() => {
        const body = bodyRef.current;
        if (!body) {
            return;
        }
        let startY = 0;
        let mode: 'sheet' | 'scroll' | null = null;
        const onStart = (event: TouchEvent) => {
            mode = null;
            if (event.touches.length === 1) {
                startY = event.touches[0].clientY;
            }
        };
        const onMove = (event: TouchEvent) => {
            if (event.touches.length !== 1) {
                return;
            }
            const y = event.touches[0].clientY;
            const dy = y - startY;
            if (mode === null && dy !== 0) {
                const up = dy < 0 && latest.current.snap !== 'full';
                const down = dy > 0 && body.scrollTop <= 0;
                mode = up || down ? 'sheet' : 'scroll';
                if (mode === 'sheet') {
                    latest.current.begin(startY);
                }
            }
            if (mode === 'sheet') {
                event.preventDefault();
                latest.current.move(y);
            }
        };
        const onEnd = () => {
            if (mode === 'sheet') {
                latest.current.end();
            }
            mode = null;
        };
        body.addEventListener('touchstart', onStart, { passive: true });
        body.addEventListener('touchmove', onMove, { passive: false });
        body.addEventListener('touchend', onEnd);
        body.addEventListener('touchcancel', onEnd);
        return () => {
            body.removeEventListener('touchstart', onStart);
            body.removeEventListener('touchmove', onMove);
            body.removeEventListener('touchend', onEnd);
            body.removeEventListener('touchcancel', onEnd);
        };
    }, []);

    const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        begin(event.clientY);
    };

    return (
        <section
            ref={sheetRef}
            className="bottom-sheet"
            aria-label={title}
            data-snap={snap}
            data-ready={heights ? true : undefined}
            data-dragging={dragging || undefined}
        >
            <button
                ref={headerRef}
                type="button"
                className="bottom-sheet__header"
                aria-expanded={snap !== 'collapsed'}
                aria-label={`${title} ${snap === 'collapsed' ? '펼치기' : '접기'}`}
                onPointerDown={handlePointerDown}
                onPointerMove={(event) => move(event.clientY)}
                onPointerUp={() => end(() => onSnapChange(toggleSnap(snap)))}
                onPointerCancel={() => end()}
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
            <div ref={bodyRef} className="bottom-sheet__body">
                {children}
            </div>
        </section>
    );
}
