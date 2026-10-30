// 걷기 안내를 소리로 읽어 준다. 같은 안내는 한 번만 읽는다.

import {
    DIRECTION_LABELS,
    type NextTurn,
    type Turn,
    type TurnDirection,
} from './turns';

// 회전 이만큼(m) 앞에서 미리 알린다.
export const PREPARE_M = 50;
// 회전 이만큼(m) 앞에서 지금 꺾으라고 알린다.
export const NOW_M = 15;

export const START_TEXT = '안내를 시작합니다.';
export const VOICE_ON_TEXT = '음성 안내를 켰습니다.';
export const REROUTE_TEXT = '경로를 다시 찾습니다.';
export const ARRIVED_TEXT = '목적지에 도착했습니다.';

const NOW_TEXTS: Record<TurnDirection, string> = {
    left: '왼쪽으로 가세요.',
    right: '오른쪽으로 가세요.',
    slight_left: '약간 왼쪽으로 가세요.',
    slight_right: '약간 오른쪽으로 가세요.',
    sharp_left: '크게 왼쪽으로 가세요.',
    sharp_right: '크게 오른쪽으로 가세요.',
    uturn: '되돌아가세요.',
};

export type Announcement = {
    /** 읽었다고 표시할 안내. 다시 읽지 않는다. */
    keys: string[];
    text: string;
};

/** 읽기 좋은 거리. 10m 단위로 반올림하고 1km 부터는 킬로미터 */
export function spokenDistance(meters: number): string {
    if (meters >= 1000) {
        return `${(meters / 1000).toFixed(1)}킬로미터`;
    }
    return `${Math.max(10, Math.round(meters / 10) * 10)}미터`;
}

/** 같은 모퉁이는 경로를 다시 찾아도 같은 이름이 되도록 좌표로 부른다. */
function turnKey({ position: [lng, lat], direction }: Turn): string {
    return `${lng.toFixed(5)},${lat.toFixed(5)},${direction}`;
}

/** 지금 읽을 안내. 이미 읽은 것(announced)이거나 아직 멀면 null */
export function announcement(
    next: NextTurn,
    arrived: boolean,
    announced: ReadonlySet<string>,
): Announcement | null {
    if (arrived) {
        return announced.has('goal:arrived')
            ? null
            : { keys: ['goal:arrived'], text: ARRIVED_TEXT };
    }
    const { turn, distanceM } = next;
    const id = turn ? turnKey(turn) : 'goal';
    const prepareKey = `${id}:prepare`;
    const nowKey = `${id}:now`;
    if (turn && distanceM <= NOW_M) {
        // 바로 앞에서 처음 알게 되면 미리 알림은 건너뛴다.
        return announced.has(nowKey)
            ? null
            : { keys: [prepareKey, nowKey], text: NOW_TEXTS[turn.direction] };
    }
    if (distanceM > PREPARE_M || announced.has(prepareKey)) {
        return null;
    }
    // 도착은 바로 앞 알림 대신 도착했을 때 알린다.
    const text = turn
        ? `${spokenDistance(distanceM)} 앞에서 ${DIRECTION_LABELS[turn.direction]}입니다.`
        : `${spokenDistance(distanceM)} 앞에 목적지가 있습니다.`;
    return { keys: [prepareKey], text };
}

export function canSpeak(): boolean {
    return 'speechSynthesis' in globalThis;
}

/** 읽던 안내를 멈춘다. */
export function stopSpeaking(
    synth: SpeechSynthesis | undefined = globalThis.speechSynthesis,
): void {
    synth?.cancel();
}

/** 한국어로 읽는다. 앞 안내가 아직 읽히는 중이면 끊고 새 안내를 읽는다. */
export function speak(
    text: string,
    synth: SpeechSynthesis | undefined = globalThis.speechSynthesis,
): void {
    if (!synth) {
        return;
    }
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ko-KR';
    synth.speak(utterance);
}
