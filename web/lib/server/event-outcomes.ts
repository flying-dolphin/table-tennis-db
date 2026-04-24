import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

type ManualEventOverride = {
  presentation_mode: 'staged_round_robin';
  sub_event_type_code: string;
  podium: {
    champion: string;
  };
};

type ChampionRecordInput = {
  eventId: number | null;
  subEventTypeCode: string | null;
  stage: string | null;
  round: string | null;
  didWin: boolean;
  playerCountry: string | null;
};

const manualEventOverrideCache = new Map<number, ManualEventOverride | null>();

export function readManualEventOverride(eventId: number): ManualEventOverride | null {
  if (manualEventOverrideCache.has(eventId)) {
    return manualEventOverrideCache.get(eventId) ?? null;
  }

  const file = path.join(process.cwd(), 'data', 'manual_event_overrides', `${eventId}.json`);
  if (!existsSync(file)) {
    manualEventOverrideCache.set(eventId, null);
    return null;
  }

  try {
    const parsed = JSON.parse(readFileSync(file, 'utf-8')) as ManualEventOverride;
    manualEventOverrideCache.set(eventId, parsed);
    return parsed;
  } catch {
    manualEventOverrideCache.set(eventId, null);
    return null;
  }
}

export function isChampionRecord(input: ChampionRecordInput) {
  if (input.didWin && input.stage === 'Main Draw' && input.round === 'Final') {
    return true;
  }

  if (input.eventId == null || !input.playerCountry || !input.subEventTypeCode) {
    return false;
  }

  const override = readManualEventOverride(input.eventId);
  return (
    override?.presentation_mode === 'staged_round_robin' &&
    input.subEventTypeCode === override.sub_event_type_code &&
    input.playerCountry === override.podium.champion
  );
}
