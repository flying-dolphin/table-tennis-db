#!/usr/bin/env python3
"""
ITTF Events Calendar 翻译脚本

用于翻译已存在的赛事日历 JSON 文件，无需重新抓取。
支持批量翻译，每多条记录合并提交一次 LLM，节省 token。

用法:
    python translate_events_calendar.py --input data/events_calendar/events_calendar_2026.json
    python translate_events_calendar.py --year 2026 --batch-size 10
    python translate_events_calendar.py --year 2026 --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# 加载 .env 文件（ittf_rankings/.env）
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from lib.translator import Translator
from validate_events_translation import validate_translation_file

logger = logging.getLogger("translate_events")

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data" / "events_calendar"


def _standardize_date(date_str: str) -> str:
    """标准化日期格式"""
    if not date_str:
        return ""

    month_map = {
        "jan": "1月", "january": "1月",
        "feb": "2月", "february": "2月",
        "mar": "3月", "march": "3月",
        "apr": "4月", "april": "4月",
        "may": "5月",
        "jun": "6月", "june": "6月",
        "jul": "7月", "july": "7月",
        "aug": "8月", "august": "8月",
        "sep": "9月", "september": "9月",
        "oct": "10月", "october": "10月",
        "nov": "11月", "november": "11月",
        "dec": "12月", "december": "12月",
    }

    result = date_str
    for eng, chn in month_map.items():
        result = result.lower().replace(eng, chn)

    return result


def _call_minimax_batch(
    texts: list[str],
    api_key: str | None = None,
) -> dict[str, str] | None:
    """
    批量调用 MiniMax API 翻译多条文本

    Args:
        texts: 要翻译的文本列表
        api_key: API 密钥

    Returns:
        dict: {原文: 译文}，如果失败返回 None
    """
    if not texts:
        return {}

    api_key = api_key or os.environ.get("MINIMAX_API_KEY") 
    if not api_key:
        logger.error("未配置 MiniMax API Key")
        return None

    # 构建批量翻译的 prompt
    # 格式：原文|译文，每行一条
    items_text = "\n".join(texts)

    system_prompt = """你是一个专业的乒乓球赛事翻译助手。
请将以下英文赛事名称翻译成中文。
每行一个，格式必须严格为：原文|译文
不要添加任何解释、序号或其他内容。"""

    user_prompt = f"""请翻译以下乒乓球赛事名称：

{items_text}

格式要求：
1. 每行一个，格式为：原文|译文
2. 只返回翻译结果，不要任何解释
3. 保持原文完全一致，不要修改大小写或标点
4. 赛事名称中的 WTT、World、Championship 等保留英文"""

    try:
        import urllib.request

        api_url = 'https://api.minimax.chat/v1/text/chatcompletion_v2'

        data = json.dumps({
            "model": "MiniMax-M2.7",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1
        }).encode('utf-8')

        req = urllib.request.Request(
            api_url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            response_body = response.read().decode('utf-8')
            logger.info(f"API 原始响应: {response_body[:1000]}")
            
            # 检查 HTTP 状态码
            if response.status != 200:
                logger.error(f"API 返回错误状态码: {response.status}")
                return None
            
            result = json.loads(response_body)

            # 优先尝试标准 OpenAI 格式
            choices = result.get('choices')
            if choices and len(choices) > 0:
                reply = choices[0]['message']['content'].strip()
            else:
                # 备用：MiniMax 特有格式
                reply = result.get('reply', '')

            if not reply:
                logger.warning(f"API 返回为空, choices={choices}, result_keys={list(result.keys())}")
                return None

            # 解析返回的翻译结果
            # 格式：原文|译文
            translations = {}
            for line in reply.splitlines():
                line = line.strip()
                if '|' in line:
                    parts = line.split('|', 1)
                    if len(parts) == 2:
                        original = parts[0].strip()
                        translated = parts[1].strip()
                        if original and translated:
                            translations[original] = translated

            logger.info(f"批量翻译成功: 提交 {len(texts)} 条，解析出 {len(translations)} 条")
            return translations

    except Exception as e:
        logger.error(f"批量翻译 API 调用失败: {e}")
        return None


def _save_progress(
    output_file: Path,
    data: dict[str, Any],
    translated_events: list[dict[str, Any]],
    total_events: int,
    batch_size: int,
    success_count: int,
    failed_count: int,
    completed_batches: int,
    total_batches: int,
) -> None:
    """保存翻译进度（增量保存）"""
    output_data = {
        "year": data.get("year"),
        "url": data.get("url"),
        "scraped_at": data.get("scraped_at"),
        "source_hash": data.get("source_hash", ""),
        "translated_at": datetime.now().isoformat(),
        "batch_size": batch_size,
        "progress": {
            "completed_batches": completed_batches,
            "total_batches": total_batches,
            "processed_events": len(translated_events),
            "total_events": total_events,
        },
        "events": translated_events,
        "summary": {
            "total": total_events,
            "processed": len(translated_events),
            "translated": success_count,
            "failed": failed_count,
            "batches": total_batches,
        }
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info(f"[进度保存] 已处理 {len(translated_events)}/{total_events} 条")


def _compute_source_hash(data: dict[str, Any]) -> str:
    """计算输入数据哈希，用于断点续传完整性校验。"""
    payload = {
        "year": data.get("year"),
        "url": data.get("url"),
        "events": data.get("events", []),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _count_translation_stats(events: list[dict[str, Any]]) -> tuple[int, int]:
    """从已翻译事件回算 fully_translated/failed 计数。"""
    translated = 0
    failed = 0
    for event in events:
        if _is_event_fully_translated(event):
            translated += 1
        else:
            failed += 1
    return translated, failed


def _is_value_translated(original: str, translated: str) -> bool:
    if not original:
        return True
    if not translated:
        return False
    return translated.strip() != original.strip()


def _is_event_fully_translated(event: dict[str, Any]) -> bool:
    """事件中所有需要翻译的字段都成功转为中文时，才视为完成。"""
    name_ok = _is_value_translated(event.get("name", ""), event.get("name_zh", ""))
    location_ok = _is_value_translated(event.get("location", ""), event.get("location_zh", ""))
    return name_ok and location_ok


def _count_completed_batches(events: list[dict[str, Any]], batch_size: int) -> int:
    """只统计前缀中“完全翻译成功”的批次，用于断点续传。"""
    completed = 0
    for start in range(0, len(events), batch_size):
        batch = events[start:start + batch_size]
        if len(batch) < batch_size:
            break
        if all(_is_event_fully_translated(event) for event in batch):
            completed += 1
            continue
        break
    return completed


def _validate_resume_data(
    existing_data: dict[str, Any],
    total_events: int,
    total_batches: int,
    batch_size: int,
    source_hash: str,
) -> tuple[bool, str]:
    """校验已有输出是否可用于继续翻译。"""
    progress = existing_data.get("progress", {})
    completed_batches = int(progress.get("completed_batches", 0) or 0)
    processed_events = int(progress.get("processed_events", 0) or 0)
    existing_events = existing_data.get("events", [])
    existing_total = int(progress.get("total_events", 0) or 0)
    existing_source_hash = existing_data.get("source_hash", "")

    if existing_source_hash and existing_source_hash != source_hash:
        return False, "source_hash 不匹配"
    if existing_total and existing_total != total_events:
        return False, "total_events 不匹配"
    if completed_batches < 0 or completed_batches > total_batches:
        return False, "completed_batches 超出范围"
    if processed_events < 0 or processed_events > total_events:
        return False, "processed_events 超出范围"
    if not isinstance(existing_events, list):
        return False, "events 结构非法"
    if len(existing_events) != processed_events:
        return False, "processed_events 与 events 长度不一致"

    return True, ""


def translate_events(
    input_file: Path,
    output_file: Path | None = None,
    skip_existing: bool = True,
    batch_size: int = 10,
    resume: bool = True,
) -> dict[str, Any]:
    """
    翻译赛事日历文件（批量翻译版，支持断点续传）

    Args:
        input_file: 输入的 JSON 文件路径
        output_file: 输出的 JSON 文件路径（默认添加 _cn 后缀）
        skip_existing: 如果输出文件已存在，是否跳过
        batch_size: 每批翻译的记录数量
        resume: 是否支持断点续传（默认 True）

    Returns:
        结果字典
    """
    if not input_file.exists():
        return {"success": False, "error": f"输入文件不存在: {input_file}"}

    # 确定输出路径
    if output_file is None:
        stem = input_file.stem
        if not stem.endswith("_cn"):
            stem = f"{stem}_cn"
        output_file = input_file.parent / f"{stem}.json"

    # 读取原始数据
    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON 解析失败: {e}"}

    events = data.get("events", [])
    if not events:
        return {"success": False, "error": "没有找到赛事数据"}

    total_events = len(events)
    total_batches = (total_events + batch_size - 1) // batch_size
    source_hash = _compute_source_hash(data)

    # 检查是否已存在翻译文件（用于断点续传）
    if resume and output_file.exists():
        try:
            existing_data = json.loads(output_file.read_text(encoding="utf-8"))
            valid, reason = _validate_resume_data(
                existing_data=existing_data,
                total_events=total_events,
                total_batches=total_batches,
                batch_size=batch_size,
                source_hash=source_hash,
            )
            if valid:
                existing_progress = existing_data.get("progress", {})
                completed_batches = int(existing_progress.get("completed_batches", 0) or 0)
                existing_events = existing_data.get("events", [])
                completed_batches = _count_completed_batches(existing_events, batch_size)
                translated_events = existing_events[:completed_batches * batch_size]
                if completed_batches > 0:
                    logger.info(f"发现已成功翻译批次: {completed_batches}/{total_batches}")
                    logger.info(f"将从第 {completed_batches + 1} 批次继续翻译...")
                else:
                    logger.info("未发现可复用的完整翻译批次，将从头翻译")
            else:
                logger.warning(f"已有输出不满足续传条件，回退从头翻译: {reason}")
                translated_events = []
                completed_batches = 0
        except (json.JSONDecodeError, KeyError):
            translated_events = []
            completed_batches = 0
    else:
        translated_events = []
        completed_batches = 0

    # 如果全部完成且 skip_existing，跳过
    if (
        skip_existing
        and completed_batches >= total_batches
        and len(translated_events) == total_events
        and all(_is_event_fully_translated(event) for event in translated_events)
    ):
        logger.info(f"翻译已完成，跳过: {output_file}")
        existing_data = json.loads(output_file.read_text(encoding="utf-8"))
        validation = validate_translation_file(output_file, input_file)
        if not validation.get("ok"):
            return {
                "success": False,
                "error": f"已存在翻译文件校验失败: {validation.get('checks', [])}",
                "data": existing_data,
                "output_file": str(output_file),
                "partial": True,
            }
        return {
            "success": True,
            "data": existing_data,
            "output_file": str(output_file),
            "skipped": True,
        }

    logger.info(f"开始翻译 {total_events} 个赛事（每批 {batch_size} 条，共 {total_batches} 批）...")
    logger.info(f"输出文件: {output_file}")

    # 批量翻译所有事件
    success_count, failed_count = _count_translation_stats(translated_events)

    # 初始化 Translator（复用词典，支持分词查词典 + 批量API翻译）
    translator = Translator()

    try:
        for batch_idx in range(completed_batches, total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, total_events)
            batch_events = events[start:end]

            logger.info(f"[批次 {batch_idx + 1}/{total_batches}] 翻译第 {start + 1}-{end} 条...")

            # 收集该批次需要翻译的名称和地点
            names_to_translate = []
            locations_to_translate = []

            for event in batch_events:
                name = event.get("name", "")
                location = event.get("location", "")
                if name:
                    names_to_translate.append(name)
                if location:
                    locations_to_translate.append(location)

            # 批量翻译名称 - 使用 Translator 分词查词典 + 批量API
            name_translations = {}
            if names_to_translate:
                logger.info(f"  批量翻译 {len(names_to_translate)} 个赛事名称（分词查词典）...")
                name_result = translator.translate_batch(names_to_translate, category="events")
                name_translations.update(name_result)
                time.sleep(0.5)

            # 批量翻译地点 - 使用 Translator 分词查词典 + 批量API
            location_translations = {}
            if locations_to_translate:
                logger.info(f"  批量翻译 {len(locations_to_translate)} 个地点（分词查词典）...")
                location_result = translator.translate_batch(locations_to_translate, category="locations")
                location_translations.update(location_result)
                time.sleep(0.5)

            # 应用翻译结果
            for event in batch_events:
                name = event.get("name", "")
                location = event.get("location", "")

                translated = event.copy()

                # 应用名称翻译
                if name:
                    if name in name_translations:
                        translated["name_zh"] = name_translations[name]
                        translated["name_translation_method"] = "translated"
                        if name_translations[name] != name:
                            logger.info(f"    {name[:40]} -> {name_translations[name][:40]}")
                    else:
                        translated["name_zh"] = name
                        translated["name_translation_method"] = "unchanged"

                # 应用地点翻译
                if location:
                    if location in location_translations:
                        translated["location_zh"] = location_translations[location]
                        translated["location_translation_method"] = "translated"
                    else:
                        translated["location_zh"] = location
                        translated["location_translation_method"] = "unchanged"

                # 日期标准化
                if event.get("date"):
                    translated["date_standardized"] = _standardize_date(event["date"])

                translated_events.append(translated)

            success_count, failed_count = _count_translation_stats(translated_events)

            # ✅ 每批次翻译完成后立即保存进度
            _save_progress(
                output_file=output_file,
                data={**data, "source_hash": source_hash},
                translated_events=translated_events,
                total_events=total_events,
                batch_size=batch_size,
                success_count=success_count,
                failed_count=failed_count,
                completed_batches=_count_completed_batches(translated_events, batch_size),
                total_batches=total_batches,
            )

            # 每批次之间稍微停顿
            if batch_idx < total_batches - 1:
                time.sleep(1)

    except KeyboardInterrupt:
        logger.warning("用户中断，保留已翻译的结果")
        completed_batches_safe = _count_completed_batches(translated_events, batch_size)
        _save_progress(
            output_file=output_file,
            data={**data, "source_hash": source_hash},
            translated_events=translated_events,
            total_events=total_events,
            batch_size=batch_size,
            success_count=success_count,
            failed_count=failed_count,
            completed_batches=completed_batches_safe,
            total_batches=total_batches,
        )
        return {
            "success": False,
            "error": "用户中断",
            "data": None,
            "output_file": str(output_file),
            "partial": True,
        }

    # 构建最终输出数据
    output_data = {
        "year": data.get("year"),
        "url": data.get("url"),
        "scraped_at": data.get("scraped_at"),
        "source_hash": source_hash,
        "translated_at": datetime.now().isoformat(),
        "batch_size": batch_size,
        "progress": {
            "completed_batches": _count_completed_batches(translated_events, batch_size),
            "total_batches": total_batches,
            "processed_events": len(translated_events),
            "total_events": total_events,
        },
        "events": translated_events,
        "summary": {
            "total": total_events,
            "processed": len(translated_events),
            "translated": success_count,
            "failed": failed_count,
            "batches": total_batches,
        }
    }

    # 保存最终结果
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info(f"翻译完成，已保存: {output_file}")

    validation = validate_translation_file(output_file, input_file)
    all_translated = failed_count == 0 and len(translated_events) == total_events
    all_translated = all_translated and bool(validation.get("ok"))

    return {
        "success": all_translated,
        "data": output_data,
        "output_file": str(output_file),
        "partial": not all_translated,
        "error": None if all_translated else f"仍有未翻译成功的事件或校验失败: {validation.get('checks', [])}",
        "stats": {
            "total": total_events,
            "translated": success_count,
            "failed": failed_count,
            "batches": total_batches,
        }
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ITTF Events Calendar 翻译脚本 - 翻译已存在的赛事日历（批量版）"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="输入的 JSON 文件路径",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="输出的 JSON 文件路径（默认添加 _cn 后缀）",
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        help="年份（自动查找 data/events_calendar/events_calendar_{year}.json）",
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=10,
        help="每批翻译的记录数量（默认: 10）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新翻译（忽略已有进度）",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="禁用断点续传（从头开始翻译）",
    )
    return parser


def main() -> None:
    # 配置根日志，确保 INFO 级别消息可见
    logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
    parser = build_parser()
    args = parser.parse_args()

    # 确定输入文件
    if args.input:
        input_file = Path(args.input)
    elif args.year:
        input_file = DEFAULT_DATA_DIR / f"events_calendar_{args.year}.json"
    else:
        logger.error("请指定 --input 或 --year 参数")
        sys.exit(1)

    # 确定输出文件
    output_file = Path(args.output) if args.output else None

    try:
        result = translate_events(
            input_file=input_file,
            output_file=output_file,
            skip_existing=not args.force,
            batch_size=args.batch_size,
            resume=not args.no_resume,
        )

        if result.get("success"):
            if result.get("skipped"):
                logger.info(f"✅ 已存在翻译文件，跳过: {result['output_file']}")
            else:
                stats = result.get("stats", {})
                logger.info("=" * 50)
                logger.info("翻译完成！")
                logger.info(f"总赛事数: {stats.get('total', 0)}")
                logger.info(f"成功翻译: {stats.get('translated', 0)}")
                logger.info(f"翻译失败: {stats.get('failed', 0)}")
                logger.info(f"批次数: {stats.get('batches', 0)}")
                logger.info(f"输出文件: {result['output_file']}")
                logger.info("=" * 50)
        elif result.get("partial"):
            logger.error(f"翻译未全部成功: {result.get('error', '存在未翻译事件')}")
            logger.info(f"已翻译的结果已保存: {result['output_file']}")
            sys.exit(1)
        else:
            logger.error(f"翻译失败: {result.get('error', '未知错误')}")
            if os.path.exists(result.get('output_file', '')):
                logger.info(f"已翻译的结果已保存: {result['output_file']}")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("用户中断")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
