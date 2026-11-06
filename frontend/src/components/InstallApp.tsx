import { useInstallApp } from '../hooks/useInstallApp';

/** My 탭 아래 '앱 설치'. 설치할 수 없거나 이미 앱으로 열었으면 숨긴다. */
export default function InstallApp() {
    const { mode, install } = useInstallApp();
    if (mode === 'installed' || mode === 'unsupported') {
        return null;
    }
    return (
        <section className="install-app" aria-label="앱 설치">
            <h3 className="my-tab__heading">앱 설치</h3>
            {mode === 'prompt' ? (
                <>
                    <p className="install-app__text">
                        홈 화면에 추가하면 앱처럼 바로 열 수 있습니다.
                    </p>
                    <button
                        type="button"
                        className="install-app__button"
                        onClick={() => void install()}
                    >
                        홈 화면에 앱 설치
                    </button>
                </>
            ) : (
                <p className="install-app__text">
                    공유 버튼을 누르고 ‘홈 화면에 추가’를 고르면 앱처럼 바로 열
                    수 있습니다.
                </p>
            )}
        </section>
    );
}
