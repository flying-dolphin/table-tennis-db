#!/usr/bin/env python3
"""
乒乓球运动员名字 LLM 翻译脚本

读取 update_players.txt 的运动员名单，使用 LLM 根据官方中文人名译名规范进行翻译。
输出格式：英文名:中文名:players

特性：
- 逐批翻译，每批完成后立即写入文件，中断不丢数据
- 自动跳过已翻译的条目（断点续传）
- 支持多 LLM 提供商

使用方式：
    python translate_player_names.py
    python translate_player_names.py --provider kimi --model kimi-k2.5
    python translate_player_names.py --batch-size 50   # 每批翻译 50 个
    python translate_player_names.py --resume          # 跳过输出文件中已有的条目
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.translator import LLMTranslator

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_FILE = PROJECT_ROOT / "tmp" / "update_players.txt"
OUTPUT_FILE = PROJECT_ROOT / "tmp" / "update_players_translated.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_player_names(file_path: Path) -> list[str]:
    """加载运动员名单"""
    names = []
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            name = line.strip()
            if name:
                names.append(name)
    return names


def load_translated(output_file: Path) -> set[str]:
    """从输出文件中读取已翻译的英文名（用于断点续传）"""
    if not output_file.exists():
        return set()
    done = set()
    with open(output_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    done.add(parts[0])
    return done


def split_batches(names: list[str], batch_size: int) -> list[list[str]]:
    """按批次大小拆分名单"""
    return [names[i:i + batch_size] for i in range(0, len(names), batch_size)]


def main() -> int:
    parser = argparse.ArgumentParser(description="翻译乒乓球运动员名字（逐批保存）")
    parser.add_argument("--input", type=str, default=str(INPUT_FILE), help="输入文件路径")
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE), help="输出文件路径")
    parser.add_argument("--provider", type=str, default="minimax", help="LLM 提供商 (minimax/kimi/qwen/glm/deepseek)")
    parser.add_argument("--model", type=str, help="LLM 模型名称")
    parser.add_argument("--batch-size", type=int, default=50, help="每批翻译的条数（默认 50）")
    parser.add_argument("--api-key", type=str, help="API Key（默认从环境变量读取）")
    parser.add_argument("--resume", action="store_true", default=True, help="跳过已翻译的条目（默认开启）")
    parser.add_argument("--no-resume", action="store_false", dest="resume", help="不跳过，从头翻译")
    args = parser.parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output)

    if not input_file.exists():
        logger.error(f"输入文件不存在: {input_file}")
        return 1

    # 加载名单
    all_names = load_player_names(input_file)
    logger.info(f"输入名单共 {len(all_names)} 条")

    # 断点续传：跳过已翻译的名字
    already_done: set[str] = set()
    if args.resume:
        already_done = load_translated(output_file)
        if already_done:
            logger.info(f"已翻译 {len(already_done)} 条，跳过")

    pending = [n for n in all_names if n not in already_done]
    if not pending:
        logger.info("所有名字已翻译完毕，无需重新翻译")
        return 0
    logger.info(f"待翻译 {len(pending)} 条")

    # 初始化翻译器
    translator_kwargs: dict = {"provider": args.provider}
    if args.model:
        translator_kwargs["model"] = args.model
    if args.api_key:
        translator_kwargs["api_key"] = args.api_key

    translator = LLMTranslator(**translator_kwargs)
    logger.info(f"使用 {translator.provider} ({translator.model})")

    if not translator.api_key:
        logger.error(f"未配置 API Key，请在 .env 中设置或通过 --api-key 传入")
        return 1

    # 准备输出文件（续写模式）
    output_file.parent.mkdir(parents=True, exist_ok=True)
    out_f = open(output_file, "a", encoding="utf-8")

    # 逐批翻译并实时写入
    batches = split_batches(pending, args.batch_size)
    total_batches = len(batches)
    total_ok = 0
    total_fail = 0

    try:
        for i, batch in enumerate(batches, 1):
            logger.info(f"批次 {i}/{total_batches}，本批 {len(batch)} 条")

            items = {name: name for name in batch}
            result = translator._translate_batch(items, category="player_names")

            if not result:
                logger.error(f"批次 {i}/{total_batches} 翻译失败，写入原文占位")
                result = {}

            # 逐条写入文件，保持顺序
            lines = []
            for name in batch:
                translated = result.get(name, name)
                lines.append(f"{name}:{translated}:players\n")
                if translated != name:
                    total_ok += 1
                else:
                    total_fail += 1

            out_f.writelines(lines)
            out_f.flush()  # 立即刷新到磁盘

            translated_in_batch = sum(1 for name in batch if result.get(name, name) != name)
            logger.info(f"批次 {i}/{total_batches} 完成：{translated_in_batch}/{len(batch)} 条已翻译，已写入")

    except KeyboardInterrupt:
        logger.warning("用户中断，已保存当前进度到输出文件")
    finally:
        out_f.close()

    if translator.total_tokens["total"]:
        logger.info(
            f"Token 累计 [{translator.provider} {translator.model}]:"
            f" prompt={translator.total_tokens['prompt']},"
            f" completion={translator.total_tokens['completion']},"
            f" total={translator.total_tokens['total']}"
        )

    logger.info(f"完成：共翻译 {total_ok} 条，保持原样 {total_fail} 条")
    logger.info(f"输出文件: {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
