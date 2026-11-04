import { useCallback, useEffect, useState } from 'react';

import {
    addSavedPlace,
    deleteSavedPlace,
    fetchSavedPlaces,
    isReplacedBy,
    type SavedPlace,
    type SavedPlaceRequest,
} from '../lib/savedPlacesApi';

export type SavedPlaces = {
    places: SavedPlace[];
    /** 처음 불러오기에 실패하면(백엔드·DB가 꺼짐) false. 저장 버튼을 숨긴다. */
    available: boolean;
    error: string | null;
    add: (entry: SavedPlaceRequest) => void;
    remove: (id: number) => void;
    /** 로그인·로그아웃으로 사용자가 바뀌면 다시 불러온다. */
    reload: () => void;
};

function messageOf(reason: unknown): string {
    return reason instanceof Error ? reason.message : String(reason);
}

export function useSavedPlaces(): SavedPlaces {
    const [places, setPlaces] = useState<SavedPlace[]>([]);
    const [available, setAvailable] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [version, setVersion] = useState(0);

    useEffect(() => {
        let cancelled = false;
        fetchSavedPlaces()
            .then((found) => {
                if (!cancelled) {
                    setPlaces(found);
                    setAvailable(true);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setPlaces([]);
                    setAvailable(false);
                }
            });
        return () => {
            cancelled = true;
        };
    }, [version]);

    const add = useCallback((entry: SavedPlaceRequest) => {
        setError(null);
        addSavedPlace(entry)
            .then((saved) =>
                setPlaces((current) => [
                    saved,
                    ...current.filter((place) => !isReplacedBy(place, saved)),
                ]),
            )
            .catch((reason: unknown) => setError(messageOf(reason)));
    }, []);

    const remove = useCallback((id: number) => {
        setError(null);
        deleteSavedPlace(id)
            .then(() =>
                setPlaces((current) =>
                    current.filter((place) => place.id !== id),
                ),
            )
            .catch((reason: unknown) => setError(messageOf(reason)));
    }, []);

    const reload = useCallback(() => setVersion((current) => current + 1), []);

    return { places, available, error, add, remove, reload };
}
