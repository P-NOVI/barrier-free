import { useSyncExternalStore } from 'react';

import {
    currentInstallMode,
    type InstallMode,
    promptInstall,
    subscribeInstall,
} from '../lib/installApp';

/** 지금 이 브라우저에서 앱을 어떻게 설치할 수 있는지와 설치 창 띄우기 */
export function useInstallApp(): {
    mode: InstallMode;
    install: () => Promise<void>;
} {
    const mode = useSyncExternalStore(subscribeInstall, currentInstallMode);
    return { mode, install: promptInstall };
}
