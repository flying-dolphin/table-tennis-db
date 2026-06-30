export function getVisibleSideAvatarPlayers<T>(players: readonly T[]): T[] {
  return players.slice(0, 2);
}
