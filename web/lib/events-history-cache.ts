const EVENTS_HISTORY_STATE_KEY = "eventsRestoreKey";
const MAX_EVENTS_SNAPSHOTS = 20;

const eventsSnapshots = new Map<string, unknown>();
const snapshotOrder: string[] = [];

function createSnapshotKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `events-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function touchSnapshotKey(key: string) {
  const existingIndex = snapshotOrder.indexOf(key);
  if (existingIndex >= 0) {
    snapshotOrder.splice(existingIndex, 1);
  }
  snapshotOrder.push(key);

  while (snapshotOrder.length > MAX_EVENTS_SNAPSHOTS) {
    const oldestKey = snapshotOrder.shift();
    if (oldestKey) {
      eventsSnapshots.delete(oldestKey);
    }
  }
}

function getHistoryStateObject() {
  if (typeof window === "undefined") {
    return {};
  }
  const currentState = window.history.state;
  return currentState && typeof currentState === "object" ? currentState : {};
}

export function readEventsHistoryKey() {
  if (typeof window === "undefined") {
    return null;
  }
  const value = getHistoryStateObject()[EVENTS_HISTORY_STATE_KEY];
  return typeof value === "string" ? value : null;
}

export function ensureEventsHistoryKey() {
  if (typeof window === "undefined") {
    return null;
  }

  const currentKey = readEventsHistoryKey();
  if (currentKey) {
    return currentKey;
  }

  const nextKey = createSnapshotKey();
  window.history.replaceState(
    {
      ...getHistoryStateObject(),
      [EVENTS_HISTORY_STATE_KEY]: nextKey,
    },
    "",
    window.location.href,
  );
  return nextKey;
}

export function writeEventsHistoryKey(key: string) {
  if (typeof window === "undefined") {
    return;
  }

  window.history.replaceState(
    {
      ...getHistoryStateObject(),
      [EVENTS_HISTORY_STATE_KEY]: key,
    },
    "",
    window.location.href,
  );
}

export function readEventsSnapshot<T>(key: string) {
  const snapshot = eventsSnapshots.get(key);
  if (snapshot === undefined) {
    return null;
  }
  touchSnapshotKey(key);
  return snapshot as T;
}

export function writeEventsSnapshot<T>(key: string, snapshot: T) {
  eventsSnapshots.set(key, snapshot);
  touchSnapshotKey(key);
}
