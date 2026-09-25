import type { ReactNode } from "react";
import { Clock3 } from "lucide-react";

export const scheduleMatchCardClassName = "cv-auto block rounded-2xl bg-white px-3.5 py-3 ring-1 ring-[#e8edf8] shadow-sm";

export function scheduleStatusMeta(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "completed") {
    return { label: "已完结", className: "bg-emerald-50 text-emerald-700 ring-emerald-100" };
  }
  if (normalized === "live") {
    return { label: "进行中", className: "bg-rose-50 text-rose-700 ring-rose-100" };
  }
  if (normalized === "pending_update") {
    return { label: "待更新", className: "bg-amber-50 text-amber-700 ring-amber-100" };
  }
  if (normalized === "cancelled") {
    return { label: "已取消", className: "bg-slate-100 text-slate-500 ring-slate-200" };
  }
  if (normalized === "walkover") {
    return { label: "退赛", className: "bg-amber-50 text-amber-700 ring-amber-100" };
  }
  return { label: "未开始", className: "bg-blue-50 text-[#2d6cf6] ring-blue-100" };
}

export function ScheduleMatchCardLayout({
  eventName,
  timeLabel,
  tableNo,
  status,
  subEventLabel,
  children,
  footer,
}: {
  eventName?: string;
  timeLabel: string;
  tableNo?: string | null;
  status: string;
  subEventLabel: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const statusMeta = scheduleStatusMeta(status);

  return (
    <>
      {eventName ? (
        <h3 className="mb-3 border-b border-slate-100 pb-2.5 text-[0.92rem] font-black leading-snug text-slate-950">
          {eventName}
        </h3>
      ) : null}
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-[0.82rem] font-bold text-slate-500">
          {tableNo ? <span className="rounded-full bg-[#f3f6fb] px-2">{tableNo}</span> : null}
          <Clock3 size={14} className="shrink-0 text-[#7d95c7]" aria-hidden="true" />
          <span className="min-w-0">{timeLabel}</span>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-[0.72rem] font-black ring-1 ${statusMeta.className}`}>
          {statusMeta.label}
        </span>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="min-w-0 truncate text-[0.8rem] font-bold text-slate-400">{subEventLabel}</p>
      </div>
      <div className="mt-3 space-y-2.5">{children}</div>
      {footer}
    </>
  );
}
