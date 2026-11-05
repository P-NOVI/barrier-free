import { type RefCallback, useCallback, useState } from 'react';

/** ref 로 붙인 요소의 높이(px). 크기가 바뀔 때마다 다시 재고, 요소가 빠지면 0 으로 돌린다. */
export function useElementHeight<T extends HTMLElement>(): [
    ref: RefCallback<T>,
    height: number,
] {
    const [height, setHeight] = useState(0);
    const ref = useCallback((node: T | null) => {
        if (!node) {
            return undefined;
        }
        const observer = new ResizeObserver(() => setHeight(node.offsetHeight));
        observer.observe(node);
        return () => {
            observer.disconnect();
            setHeight(0);
        };
    }, []);
    return [ref, height];
}
