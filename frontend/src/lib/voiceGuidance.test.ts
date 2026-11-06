import { afterEach, describe, expect, it, vi } from 'vitest';

import type { NextTurn, Turn } from './turns';
import {
    announcement,
    ARRIVED_TEXT,
    speak,
    spokenDistance,
} from './voiceGuidance';

const RIGHT: Turn = {
    atM: 120,
    position: [126.971234, 37.561234],
    angle: 90,
    direction: 'right',
};

const ahead = (distanceM: number, turn: Turn | null = RIGHT): NextTurn => ({
    turn,
    distanceM,
});

/** 안내를 차례로 받아 읽은 문장 목록을 돌려준다. */
function speakAlong(steps: NextTurn[]): string[] {
    const announced = new Set<string>();
    return steps.flatMap((next) => {
        const result = announcement(next, false, announced);
        result?.keys.forEach((key) => announced.add(key));
        return result ? [result.text] : [];
    });
}

describe('spokenDistance', () => {
    it.each([
        [3, '10미터'],
        [46, '50미터'],
        [120, '120미터'],
        [1234, '1.2킬로미터'],
    ])('%dm → %s', (meters, text) => {
        expect(spokenDistance(meters)).toBe(text);
    });
});

describe('announcement', () => {
    it('회전 50m 앞에서 한 번, 바로 앞에서 한 번 읽는다', () => {
        expect(
            speakAlong([ahead(80), ahead(48), ahead(30), ahead(12), ahead(5)]),
        ).toEqual(['50미터 앞에서 오른쪽입니다.', '오른쪽으로 가세요.']);
    });

    it('바로 앞에서 처음 알면 미리 알림 없이 꺾으라고만 한다', () => {
        expect(speakAlong([ahead(10)])).toEqual(['오른쪽으로 가세요.']);
    });

    it('경로를 다시 찾아 거리가 바뀌어도 같은 모퉁이는 다시 읽지 않는다', () => {
        expect(
            speakAlong([ahead(45), ahead(40, { ...RIGHT, atM: 60 })]),
        ).toEqual(['50미터 앞에서 오른쪽입니다.']);
    });

    it('회전이 더 없으면 목적지를 미리 알리고, 도착하면 알린다', () => {
        const announced = new Set<string>();
        const goal = announcement(ahead(40, null), false, announced);
        goal?.keys.forEach((key) => announced.add(key));
        const arrived = announcement(ahead(10, null), true, announced);
        arrived?.keys.forEach((key) => announced.add(key));

        expect(goal?.text).toBe('40미터 앞에 목적지가 있습니다.');
        expect(arrived?.text).toBe(ARRIVED_TEXT);
        expect(announcement(ahead(5, null), true, announced)).toBeNull();
    });

    it('점선 구간에 들어서면 한 번 알리고, 목적지 미리 알림은 건너뛴다', () => {
        const announced = new Set<string>();
        const gap = announcement(ahead(62, null), false, announced, 'entrance');
        gap?.keys.forEach((key) => announced.add(key));

        expect(gap?.text).toBe(
            '건물 출입구 앞입니다. 점선을 따라 60미터 더 가면 목적지입니다.',
        );
        expect(
            announcement(ahead(30, null), false, announced, 'entrance'),
        ).toBeNull();
        expect(announcement(ahead(30, null), false, announced)).toBeNull();
        expect(announcement(ahead(10, null), true, announced)?.text).toBe(
            ARRIVED_TEXT,
        );
    });

    it('출입구가 아닌 점선은 길 안내가 끝났다고 알린다', () => {
        expect(
            announcement(ahead(40, null), false, new Set(), 'gap')?.text,
        ).toBe(
            '길 안내가 끝났습니다. 점선을 따라 40미터 더 가면 목적지입니다.',
        );
    });

    it('남은 회전이 있으면 점선 구간 알림보다 회전을 먼저 읽는다', () => {
        expect(
            announcement(ahead(10), false, new Set(), 'entrance')?.text,
        ).toBe('오른쪽으로 가세요.');
    });
});

describe('speak', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('앞 안내를 끊지 않고 한국어로 읽는다', () => {
        vi.stubGlobal(
            'SpeechSynthesisUtterance',
            class {
                lang = '';
                text: string;
                constructor(text: string) {
                    this.text = text;
                }
            },
        );
        const synth = { cancel: vi.fn(), speak: vi.fn() };

        speak('오른쪽으로 가세요.', synth as unknown as SpeechSynthesis);

        expect(synth.cancel).not.toHaveBeenCalled();
        expect(synth.speak).toHaveBeenCalledWith(
            expect.objectContaining({
                text: '오른쪽으로 가세요.',
                lang: 'ko-KR',
            }),
        );
    });

    it('음성 기능이 없으면 아무것도 하지 않는다', () => {
        expect(() => speak('안녕', undefined)).not.toThrow();
    });
});
