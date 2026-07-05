export function matchStatusLabel(status: string | null | undefined, winnerSide: string | null | undefined) {
  const normalized = status?.toLowerCase();

  if (normalized === "live") return "进行中";
  if (normalized === "completed") return "已结束";
  if (normalized === "walkover") return "退赛";
  if (normalized === "cancelled") return "已取消";

  return winnerSide ? "已结束" : "未开始";
}
