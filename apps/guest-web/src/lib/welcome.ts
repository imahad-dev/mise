type Store = { getItem(key: string): string | null; setItem(key: string, value: string): void };

const playedThisLoad = new Set<string>();

/** True the first time a visit's welcome may play: once per visit through sessionStorage, or once
 *  per page load when storage is missing or throws. */
export function claimWelcome(visitId: string, storage: Store | null): boolean {
  if (!visitId) return false;
  const key = `welcome:${visitId}`;
  if (playedThisLoad.has(key)) return false;
  playedThisLoad.add(key);
  try {
    if (storage?.getItem(key)) return false;
    storage?.setItem(key, "1");
  } catch {
    // Storage blocked: the in-memory record above still limits it to once per page load.
  }
  return true;
}
