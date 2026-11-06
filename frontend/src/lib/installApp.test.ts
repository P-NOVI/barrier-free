import { describe, expect, it } from 'vitest';

import { installMode, isIos } from './installApp';

const IPHONE =
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';
const MAC =
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15';
const ANDROID =
    'Mozilla/5.0 (Linux; Android 14; SM-S921N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36';

const env = (over: Partial<Parameters<typeof installMode>[0]> = {}) => ({
    standalone: false,
    installed: false,
    canPrompt: false,
    userAgent: ANDROID,
    maxTouchPoints: 5,
    ...over,
});

describe('isIos', () => {
    it.each([
        ['iPhone', IPHONE, 5, true],
        ['iPadOS 사파리는 Mac 처럼 보여도 터치가 되면 iOS', MAC, 5, true],
        ['Mac', MAC, 0, false],
        ['안드로이드', ANDROID, 5, false],
    ] as const)('%s', (_, userAgent, touchPoints, expected) => {
        expect(isIos(userAgent, touchPoints)).toBe(expected);
    });
});

describe('installMode', () => {
    it('앱으로 열었거나 방금 설치했으면 설치됨', () => {
        expect(installMode(env({ standalone: true, canPrompt: true }))).toBe(
            'installed',
        );
        expect(installMode(env({ installed: true }))).toBe('installed');
    });

    it('설치 창 이벤트가 있으면 버튼으로 띄운다', () => {
        expect(installMode(env({ canPrompt: true }))).toBe('prompt');
    });

    it('iPhone 은 공유 메뉴로 안내하고, 그 밖은 설치할 수 없다', () => {
        expect(installMode(env({ userAgent: IPHONE }))).toBe('ios');
        expect(installMode(env())).toBe('unsupported');
    });
});
