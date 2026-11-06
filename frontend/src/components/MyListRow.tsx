type MyListRowProps = {
    icon: string;
    title: string;
    detail: string;
    onPick: () => void;
    /** 없으면 지우기 버튼을 두지 않는다(아직 등록하지 않은 칸). */
    onDelete?: () => void;
    /** 아직 등록하지 않은 칸이면 흐리게 보인다. */
    empty?: boolean;
};

/** My 탭 목록 한 줄: 동그란 아이콘, 이름, 작은 글씨 설명, 지우기 */
export default function MyListRow({
    icon,
    title,
    detail,
    onPick,
    onDelete,
    empty = false,
}: MyListRowProps) {
    return (
        <li className="my-list__row" data-empty={empty || undefined}>
            <button type="button" className="my-list__pick" onClick={onPick}>
                <span className="my-list__icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                        <path d={icon} />
                    </svg>
                </span>
                <span className="my-list__text">
                    <span className="my-list__title">{title}</span>
                    <span className="my-list__detail">{detail}</span>
                </span>
            </button>
            {onDelete && (
                <button
                    type="button"
                    className="my-list__delete"
                    aria-label={`${title} 지우기`}
                    onClick={onDelete}
                >
                    ×
                </button>
            )}
        </li>
    );
}
