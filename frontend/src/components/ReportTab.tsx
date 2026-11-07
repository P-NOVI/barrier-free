import type { MyReports as MyReportsState } from '../hooks/useMyReports';
import { REPORT_KINDS } from '../lib/reportApi';
import MyReports from './MyReports';

// 큰 버튼 아이콘(24×24 선). 길찾기 입력칸 아래 버튼과 같은 모양이다.
const ICONS = {
    locate: 'M20 4 4 11l7 2 2 7Z',
    map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2ZM9 4v14M15 6v14',
};

type ReportTabProps = {
    myReports: MyReportsState;
    /** 지금 위치를 찾는 중 */
    locating: boolean;
    /** 지금 위치를 못 찾았을 때 안내 */
    locateError: string | null;
    /** 지도를 눌러 제보할 위치를 고르는 중 */
    picking: boolean;
    onReportHere: () => void;
    onPickOnMap: () => void;
};

/** 제보 탭: 제보하는 두 가지 방법, 제보 순서, 내 제보 */
export default function ReportTab({
    myReports,
    locating,
    locateError,
    picking,
    onReportHere,
    onPickOnMap,
}: ReportTabProps) {
    return (
        <div className="report-tab">
            <p className="report-tab__intro">
                길에서 불편했던 곳을 알려 주세요. 확인되면 다른 사람의 길찾기가
                그곳을 피하거나 미리 알려 줘요.
            </p>
            <div className="report-tab__actions">
                <button
                    type="button"
                    className="report-tab__action"
                    disabled={locating}
                    onClick={onReportHere}
                >
                    <span className="report-tab__icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24">
                            <path d={ICONS.locate} />
                        </svg>
                    </span>
                    <span className="report-tab__action-title">
                        {locating ? '위치 찾는 중…' : '지금 위치 제보'}
                    </span>
                    <span className="report-tab__action-detail">
                        서 있는 곳을 바로 제보해요
                    </span>
                </button>
                <button
                    type="button"
                    className="report-tab__action"
                    aria-pressed={picking}
                    onClick={onPickOnMap}
                >
                    <span className="report-tab__icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24">
                            <path d={ICONS.map} />
                        </svg>
                    </span>
                    <span className="report-tab__action-title">
                        지도에서 골라 제보
                    </span>
                    <span className="report-tab__action-detail">
                        지도를 눌러 위치를 골라요
                    </span>
                </button>
            </div>
            {locateError && (
                <p role="alert" className="place-search__error">
                    {locateError}
                </p>
            )}
            <h3 className="my-tab__heading">이렇게 제보해요</h3>
            <ol className="report-tab__steps">
                <li>위치 고르기</li>
                <li>
                    종류 고르기 ·{' '}
                    {REPORT_KINDS.map((kind) => kind.label).join(' · ')}
                </li>
                <li>사진 1장 올리기</li>
                <li>확인되면 길찾기에 반영</li>
            </ol>
            <h3 className="my-tab__heading">
                내 제보
                {myReports.available && ` ${myReports.reports.length}`}
            </h3>
            {myReports.error && (
                <p role="alert" className="my-tab__error">
                    {myReports.error}
                </p>
            )}
            {myReports.available ? (
                <MyReports
                    reports={myReports.reports}
                    onUpdate={myReports.update}
                    onDelete={myReports.remove}
                />
            ) : (
                <p className="my-tab__status">
                    불러오지 못했어요. 잠시 뒤 다시 열어 주세요.
                </p>
            )}
        </div>
    );
}
