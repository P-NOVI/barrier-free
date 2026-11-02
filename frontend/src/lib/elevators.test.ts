import { afterEach, describe, expect, it, vi } from 'vitest';

import elevatorsRaw from '../../public/data/elevators.json?raw';
import { elevatorName, fetchElevators, parseElevators } from './elevators';

const SAMPLE = {
    id: '211578',
    station: '종로3가',
    district: '종로구',
    nodeType: 1,
    position: [126.9918, 37.5725],
};

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('elevatorName', () => {
    it('역명 뒤에 엘리베이터를 붙인다', () => {
        const [elevator] = parseElevators([SAMPLE]);
        expect(elevatorName(elevator)).toBe('종로3가 엘리베이터');
    });

    it('역명이 비어 있으면 엘리베이터만 쓴다', () => {
        const [elevator] = parseElevators([{ ...SAMPLE, station: '' }]);
        expect(elevatorName(elevator)).toBe('엘리베이터');
    });
});

describe('parseElevators', () => {
    it('올바른 항목은 그대로 돌려준다', () => {
        expect(parseElevators([SAMPLE])).toEqual([SAMPLE]);
    });

    it('역명이 빈 문자열이어도 받는다', () => {
        const [elevator] = parseElevators([{ ...SAMPLE, station: '' }]);
        expect(elevator.station).toBe('');
    });

    it('배열이 아니면 실패한다', () => {
        expect(() => parseElevators({})).toThrow('배열');
    });

    it('필드 타입이 틀리면 몇 번째 항목인지 알려 준다', () => {
        expect(() =>
            parseElevators([SAMPLE, { ...SAMPLE, nodeType: '1' }]),
        ).toThrow('1번 항목');
    });

    it('좌표가 [경도, 위도] 숫자 쌍이 아니면 실패한다', () => {
        expect(() =>
            parseElevators([{ ...SAMPLE, position: [126.9918] }]),
        ).toThrow('0번 항목');
        expect(() =>
            parseElevators([{ ...SAMPLE, position: ['126.9', '37.5'] }]),
        ).toThrow('0번 항목');
    });

    // 임시 JSON 을 쓰는 동안만 둔다. /api/elevators 로 바꾸면 이 케이스도 지운다.
    it('make_elevators.py 가 만든 실제 데이터 643건이 모두 통과한다', () => {
        expect(parseElevators(JSON.parse(elevatorsRaw))).toHaveLength(643);
    });
});

describe('fetchElevators', () => {
    it('응답 JSON 을 검사해서 돌려준다', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve([SAMPLE]),
        });
        vi.stubGlobal('fetch', fetchMock);
        await expect(fetchElevators('/x.json')).resolves.toEqual([SAMPLE]);
        expect(fetchMock).toHaveBeenCalledWith('/x.json');
    });

    it('응답이 실패하면 상태 코드를 담아 실패한다', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue({ ok: false, status: 404 }),
        );
        await expect(fetchElevators()).rejects.toThrow('404');
    });
});
