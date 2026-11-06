// 이동 조건 프리셋. id 는 backend/core/profiles.py 의 PRESETS 키와 같아야 한다.

export const PRESETS = [
    { id: 'manual_wheelchair', label: '수동 휠체어' },
    { id: 'power_wheelchair', label: '전동 휠체어' },
    { id: 'stroller', label: '유모차' },
    { id: 'crutches', label: '목발' },
    { id: 'elderly', label: '고령자' },
    { id: 'general', label: '일반 보행' },
] as const;

export type PresetId = (typeof PRESETS)[number]['id'];

export const DEFAULT_PRESET: PresetId = 'general';

export function isPresetId(value: string): value is PresetId {
    return PRESETS.some((preset) => preset.id === value);
}

/** 화면에 보일 이름. 예전에 저장한 모르는 id 는 그대로 보인다. */
export function presetLabel(id: string): string {
    return PRESETS.find((preset) => preset.id === id)?.label ?? id;
}
