#!/usr/bin/env python3
"""
统一翻译命令行入口。

读取一个文本文件（每行一个待翻译词），按指定数据类型翻译，
输出每行对应的译文（保持输入顺序）。

数据类型（--type）与 scripts/data/translation_dict_v2.json 的 categories 一致：
    players / events / locations / terms / others / position / round / stage

翻译模式（--mode）：
    dict  仅词典（未命中保留原文）
    llm   仅 LLM
    both  先词典后 LLM（默认）

使用示例：
    python scripts/run_translator.py --file names.txt --type players
    python scripts/run_translator.py --file events.txt --type events --mode both --provider kimi
    python scripts/run_translator.py --file new.txt --type players --mode llm --confirm
    python scripts/run_translator.py --file new.txt --type players --confirm --output out.txt

--confirm 仅在使用 LLM 时生效：对每条 LLM 译文逐条人工确认
（accept 接受 / other 输入自定义译文 / stop 停止退出），
确认后的结果会回写词典文件。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.translator import SUPPORTED_TYPES, Translator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_terms(file_path: Path) -> list[str]:
    """读取每行一个词，去除空行与首尾空白，保持顺序。"""
    terms: list[str] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if term:
            terms.append(term)
    return terms


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="统一翻译命令行入口（每行一个词）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", required=True, help="输入文件，每行一个待翻译词")
    parser.add_argument(
        "--type",
        required=True,
        choices=SUPPORTED_TYPES,
        help="数据类型（对应词典 categories）",
    )
    parser.add_argument(
        "--mode",
        default="both",
        choices=("dict", "llm", "both"),
        help="翻译模式（默认 both）",
    )
    parser.add_argument("--provider", default="minimax", help="LLM 提供商")
    parser.add_argument("--model", default=None, help="LLM 模型")
    parser.add_argument("--api-key", default=None, help="API Key（默认从环境变量读取）")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="LLM 译文逐条人工确认，并将确认结果回写词典（仅 llm/both 生效）",
    )
    parser.add_argument(
        "--output",
        help="输出文件（默认打印到标准输出）。格式：每行 '原文<TAB>译文'",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    file_path = Path(args.file)
    if not file_path.exists():
        logger.error("输入文件不存在: %s", file_path)
        return 1

    terms = load_terms(file_path)
    if not terms:
        logger.error("输入文件为空: %s", file_path)
        return 1
    logger.info("读取 %d 行（去重后 %d 条）", len(terms), len(dict.fromkeys(terms)))

    translator = Translator(
        mode=args.mode,
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        confirm=args.confirm,
    )

    unique = list(dict.fromkeys(terms))
    results = translator.translate_batch({t: t for t in unique}, args.type)
    if results is None:
        logger.error("翻译失败")
        return 1

    if translator.stopped:
        logger.warning("用户中途停止，未确认部分保留原文")

    lines = [f"{term}\t{results.get(term, term)}" for term in terms]
    output_text = "\n".join(lines) + "\n"

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        logger.info("已写入: %s", out_path)
    else:
        sys.stdout.write(output_text)

    return 0


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
