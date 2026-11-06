// 웹앱을 홈 화면에 앱으로 설치한다(PWA).
// 크롬·엣지·삼성 인터넷은 설치 창을 띄울 수 있는 beforeinstallprompt 이벤트를 준다.
// 이 이벤트는 화면이 뜨자마자 한 번 오므로, 이 모듈을 불러올 때부터 받아 둔다.
// iPhone·iPad 는 이 이벤트가 없어 사용자가 공유 메뉴에서 직접 추가해야 한다.

/** 브라우저 설치 창 이벤트. 표준이 아니라 TypeScript DOM 타입에 없다. */
export type InstallPromptEvent = Event & {
    prompt: () => Promise<void>;
    userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

/**
 * - installed: 이미 설치한 앱으로 열었거나 방금 설치했다.
 * - prompt: 버튼으로 브라우저 설치 창을 띄울 수 있다.
 * - ios: 공유 메뉴의 '홈 화면에 추가'로 설치한다.
 * - unsupported: 이 브라우저에서는 설치할 수 없다(또는 아직 설치 조건이 안 됐다).
 */
export type InstallMode = 'installed' | 'prompt' | 'ios' | 'unsupported';

type Environment = {
    standalone: boolean;
    installed: boolean;
    canPrompt: boolean;
    userAgent: string;
    maxTouchPoints: number;
};

/** iPhone·iPad. iPadOS 사파리는 Mac 처럼 보여서 터치 지원으로 가린다. */
export function isIos(userAgent: string, maxTouchPoints: number): boolean {
    return (
        /iPhone|iPad|iPod/.test(userAgent) ||
        (/Macintosh/.test(userAgent) && maxTouchPoints > 1)
    );
}

export function installMode({
    standalone,
    installed,
    canPrompt,
    userAgent,
    maxTouchPoints,
}: Environment): InstallMode {
    if (standalone || installed) {
        return 'installed';
    }
    if (canPrompt) {
        return 'prompt';
    }
    return isIos(userAgent, maxTouchPoints) ? 'ios' : 'unsupported';
}

let deferred: InstallPromptEvent | null = null;
let installed = false;
const listeners = new Set<() => void>();

function notify() {
    listeners.forEach((listener) => listener());
}

if (typeof window !== 'undefined') {
    window.addEventListener('beforeinstallprompt', (event) => {
        // 브라우저가 알아서 띄우는 설치 안내 대신 My 탭 버튼으로 띄운다.
        event.preventDefault();
        deferred = event as InstallPromptEvent;
        notify();
    });
    window.addEventListener('appinstalled', () => {
        deferred = null;
        installed = true;
        notify();
    });
}

/** 설치 상태가 바뀌면 listener 를 부른다. 반환값으로 구독을 끊는다. */
export function subscribeInstall(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

function isStandalone(): boolean {
    return (
        window.matchMedia('(display-mode: standalone)').matches ||
        // iOS 사파리 홈 화면 앱
        ('standalone' in navigator && navigator.standalone === true)
    );
}

export function currentInstallMode(): InstallMode {
    return installMode({
        standalone: isStandalone(),
        installed,
        canPrompt: deferred !== null,
        userAgent: navigator.userAgent,
        maxTouchPoints: navigator.maxTouchPoints,
    });
}

/** 브라우저 설치 창을 띄운다. 설치 창은 이벤트 하나에 한 번만 띄울 수 있다. */
export async function promptInstall(): Promise<void> {
    const event = deferred;
    if (!event) {
        return;
    }
    deferred = null;
    await event.prompt();
    await event.userChoice;
    notify();
}
