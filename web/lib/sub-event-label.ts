const SUB_EVENT_SHORT_NAME_MAP: Record<string, string> = {
  WS: "女单",
  WD: "女双",
  WT: "女团",
  XD: "混双",
  XT: "混团",
  MS: "男单",
  MD: "男双",
  MT: "男团",
};

export function getSubEventShortName(code: string | null | undefined): string | null {
  if (!code) return null;
  return SUB_EVENT_SHORT_NAME_MAP[code] ?? null;
}

export function formatSubEventLabel(
  code: string | null | undefined,
  fallbackNameZh?: string | null,
  emptyLabel: string = "项目待补",
): string {
  return getSubEventShortName(code) || fallbackNameZh || code || emptyLabel;
}
