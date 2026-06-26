#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取指定 event 的 "Event Info" 赛事日程（Provisional Schedule）并翻译成中文。

数据来源：WTT eventInfo 页面 (https://www.worldtabletennis.com/eventInfo?eventId={id})
"Event Info" 标签页透出的 "Provisional Schedule" 区块，其数据来自后端接口：

    https://liveeventsapi.worldtabletennis.com/api/cms/event_provisional_schedule/list/{eventId}

返回里的 ``provisional_data`` 是一段 JSON 字符串，逐行对应页面表格的一行
(SESSION | VENUE | TABLES | START TIME | EVENT)。

本脚本把每一行整理为中文条目，参考 data/event_schedule/3216.json 的字段口径
（日期 / 时间 / 赛事 / 球台 / 场馆），并补充页面同样透出的 "场次"。与 3216 的
区别在于：3242 这类赛事在页面上透出的是「具体哪几张球台」而不是球台数，所以这里
保留具体球台标识（如 "1号台" / "2-4号台"）。

翻译复用 scripts/lib/translator.py 的统一 Translator。

用法：
    python scripts/scrape_event_schedule.py --event-id 3242
    python scripts/scrape_event_schedule.py --event-id 3242 --mode dict-then-llm --provider minimax
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from lib.translator import Translator  # noqa: E402

PROVISIONAL_SCHEDULE_URL = (
    "https://liveeventsapi.worldtabletennis.com/api/cms/event_provisional_schedule/list/{event_id}"
)

REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.worldtabletennis.com",
    "Referer": "https://www.worldtabletennis.com/",
}

OUTPUT_DIR = PROJECT_ROOT / "data" / "event_schedule"

# CLI mode -> Translator mode
_MODE_MAP = {"dict": "dict", "llm": "llm", "dict-then-llm": "both"}


def fetch_provisional_schedule(event_id: int) -> list[dict]:
    """拉取 Provisional Schedule 接口，返回解析后的逐行 schedule 数据。"""
    url = PROVISIONAL_SCHEDULE_URL.format(event_id=event_id)
    req = urllib.request.Request(url, headers=REQ_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"event {event_id} 没有 Provisional Schedule 数据")

    # 优先英文记录（lang_ID == 1 / publishOrg == wtt），其 provisional_data 才是完整表格
    record = None
    for item in payload:
        if item.get("provisional_data"):
            if item.get("lang_ID") == 1 or item.get("publishOrg") == "wtt":
                record = item
                break
    if record is None:
        for item in payload:
            if item.get("provisional_data"):
                record = item
                break
    if record is None:
        raise RuntimeError(f"event {event_id} 的 Provisional Schedule 为空")

    rows = json.loads(record["provisional_data"])
    if not isinstance(rows, list):
        raise RuntimeError(f"event {event_id} 的 provisional_data 结构异常")
    return rows


def format_date(value: str | None) -> str:
    """2026-06-26 -> 6月26日。无法解析时原样返回。"""
    if not value:
        return ""
    parts = value.split("-")
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        return f"{int(parts[1])}月{int(parts[2])}日"
    return value


def format_time(value: str | None) -> str:
    """1000 -> 10:00，1730 -> 17:30。无法解析时原样返回。"""
    if not value:
        return ""
    digits = value.strip()
    if digits.isdigit() and len(digits) in (3, 4):
        digits = digits.zfill(4)
        return f"{digits[:2]}:{digits[2:]}"
    return value


def format_tables(value: str | None) -> str:
    """'1' -> '1号台'，'2 - 4' -> '2-4号台'，'' -> ''。"""
    if not value:
        return ""
    normalized = "-".join(part.strip() for part in value.replace("–", "-").split("-") if part.strip())
    if not normalized:
        return ""
    return f"{normalized}号台"


def split_competition(value: str | None) -> list[str]:
    """'Men's Singles R64 + Women's Singles R64' -> 两个分段。"""
    if not value:
        return []
    return [seg.strip() for seg in value.split("+") if seg.strip()]


# 英文赛事分项 -> sub_event_code（与 scripts/runtime/wtt_import_shared.SUB_EVENT_MAP 一致）
_SUB_EVENT_EN = {
    "Men's Teams": "MT",
    "Women's Teams": "WT",
    "Mixed Teams": "XT",
    "Men's Singles": "MS",
    "Women's Singles": "WS",
    "Men's Doubles": "MD",
    "Women's Doubles": "WD",
    "Mixed Doubles": "XD",
}

# 英文轮次 -> round_code
_ROUND_EN = {
    "R256": "R256", "R128": "R128", "R64": "R64", "R48": "R48",
    "R32": "R32", "R24": "R24", "R16": "R16", "R8": "R8",
    "QF": "QF", "SF": "SF", "F": "F", "FINAL": "F",
    "BR": "BR", "BRONZE": "BR",
}


def parse_competition_segment_en(segment: str) -> dict | None:
    """从英文赛事分段解析出 {sub_event_code, stage_code, round_code}。

    例：
        "Men's Singles Qualifying R1" -> MS / PRELIMINARY / R1
        "Women's Singles R64"         -> WS / MAIN_DRAW / R64
        "Mixed Doubles Final"         -> XD / MAIN_DRAW / F
    无法识别分项时返回 None。
    """
    seg = " ".join(segment.split()).strip()
    if not seg:
        return None

    sub_code = None
    rest = seg
    # 取最长匹配的分项前缀
    for name in sorted(_SUB_EVENT_EN, key=len, reverse=True):
        if seg.startswith(name):
            sub_code = _SUB_EVENT_EN[name]
            rest = seg[len(name):].strip()
            break
    if sub_code is None:
        return None

    upper = rest.upper()
    if "QUALIF" in upper or "QUAL." in upper:
        stage_code = "PRELIMINARY"
        m = re.search(r"R\s*0*(\d+)", upper)
        round_code = f"R{int(m.group(1))}" if m else "UNKNOWN"
        return {"sub_event_code": sub_code, "stage_code": stage_code, "round_code": round_code}

    round_code = "UNKNOWN"
    token = upper.replace(" ", "")
    for key, code in _ROUND_EN.items():
        if token == key or token.startswith(key):
            round_code = code
            break
    else:
        m = re.search(r"R\s*0*(\d+)", upper)
        if m:
            round_code = f"R{int(m.group(1))}"

    return {"sub_event_code": sub_code, "stage_code": "MAIN_DRAW", "round_code": round_code}


def parse_competition_en(competition: str | None) -> list[dict]:
    """整行英文 competition -> 结构化轮次列表（供导入侧落到 parsed_rounds_json）。"""
    parsed: list[dict] = []
    for seg in split_competition(competition):
        item = parse_competition_segment_en(seg)
        if item is not None:
            parsed.append(item)
    return parsed


def build_translation_inputs(rows: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """收集需要翻译的唯一英文字符串：赛事分段、场次。

    场馆名称按需求保留原始英文，不翻译。
    """
    competitions: dict[str, str] = {}
    sessions: dict[str, str] = {}
    for row in rows:
        for seg in split_competition(row.get("competition")):
            competitions[seg] = seg
        title = (row.get("sessionTitle") or "").strip()
        if title:
            sessions[title] = title
    return competitions, sessions


# 汉字 / 中文标点字符集，用于清理 LLM 在中英混排时插入的多余空格
_CJK = r"一-鿿　-〿＀-￯"


def tidy_cn(text: str) -> str:
    """去掉中文与数字/英文之间多余的空格，使 "第 1 节" -> "第1节"。"""
    if not text:
        return text
    text = re.sub(rf"(?<=[{_CJK}])\s+(?=[0-9A-Za-z/])", "", text)
    text = re.sub(rf"(?<=[0-9A-Za-z/])\s+(?=[{_CJK}])", "", text)
    return text.strip()


def translate_map(translator: Translator, items: dict[str, str], data_type: str) -> dict[str, str]:
    """翻译一组 {text: text}，返回 {原文: 译文}；为空或失败时回退原文。"""
    if not items:
        return {}
    results = translator.translate_batch(items, data_type)
    if results is None:
        print(f"  ! {data_type} 翻译失败，回退原文", file=sys.stderr)
        return dict(items)
    return {key: tidy_cn(value) for key, value in results.items()}


def build_schedule(rows: list[dict], translator: Translator) -> list[dict]:
    competitions, sessions = build_translation_inputs(rows)

    print(f"待翻译：赛事分段 {len(competitions)}，场次 {len(sessions)}（场馆保留英文原名）")
    comp_cn = translate_map(translator, competitions, "others")
    session_cn = translate_map(translator, sessions, "others")

    schedule: list[dict] = []
    for row in rows:
        events = [comp_cn.get(seg, seg) for seg in split_competition(row.get("competition"))]
        entry = {
            "日期": format_date(row.get("date")),
            "场次": session_cn.get((row.get("sessionTitle") or "").strip(), row.get("sessionTitle") or ""),
            "时间": format_time(row.get("startTime")),
            "赛事": events,
            "球台": format_tables(row.get("tables")),
            "场馆": (row.get("venue") or "").strip(),
            # 机器可读字段：由可靠的英文 competition 解析得到，供导入侧落到 parsed_rounds_json
            "_parsed": parse_competition_en(row.get("competition")),
        }
        schedule.append(entry)
    return schedule


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取并翻译 WTT Event Info 赛事日程")
    parser.add_argument("--event-id", type=int, required=True, help="WTT eventId，例如 3242")
    parser.add_argument(
        "--mode",
        choices=("dict", "llm", "dict-then-llm"),
        default="dict-then-llm",
        help="翻译模式（默认先查词典再走 LLM）",
    )
    parser.add_argument("--provider", default=None, help="LLM provider（默认读取 DEFAULT_PROVIDER 或 minimax）")
    parser.add_argument("--model", default=None, help="LLM model")
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="输出目录（默认 data/event_schedule/）",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    print(f"抓取 event {args.event_id} 的 Provisional Schedule …")
    try:
        rows = fetch_provisional_schedule(args.event_id)
    except urllib.error.HTTPError as exc:
        print(f"接口请求失败：HTTP {exc.code}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"抓取失败：{exc}", file=sys.stderr)
        return 1
    print(f"共 {len(rows)} 行日程")

    translator = Translator(mode=_MODE_MAP[args.mode], provider=args.provider, model=args.model)
    schedule = build_schedule(rows, translator)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.event_id}.json"
    out_path.write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写入 {out_path}（{len(schedule)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
