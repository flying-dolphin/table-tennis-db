export function formatPoints(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

export function changeLabel(change: number) {
  if (change > 0) return `↑ ${change}`;
  if (change < 0) return `↓ ${Math.abs(change)}`;
  return '保持';
}

export function changeTone(change: number) {
  if (change > 0) return 'up';
  if (change < 0) return 'down';
  return 'same';
}

export function slugifyName(name: string) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
