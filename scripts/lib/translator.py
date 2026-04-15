#!/usr/bin/env python3
"""
纯 LLM 翻译模块

功能：
- 接收 dict[str, str] (key -> value)，只翻译 value，key 作为上下文参考
- 自动按大小拆分批次提交 LLM
- 返回 dict[str, str] (key -> translated_value)

支持的 API：
- MiniMax（默认）

使用方法：
    from lib.translator import LLMTranslator

    translator = LLMTranslator()
    results = translator.translate({"Ma Long": "Ma Long", "event_name": "World Championships"})
    # => {"Ma Long": "马龙", "event_name": "世界锦标赛"}
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 1024  # 单批次最大字符数


class LLMTranslator:
    """纯 LLM 翻译器

    API Key 优先级：
    1. 传入的参数 api_key
    2. 环境变量 MINIMAX_API_KEY（从 .env 文件自动加载）
    """

    def __init__(self, api_key: str | None = None, provider: str = "minimax"):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY")
        self.provider = provider.lower()

    def translate(
        self, items: dict[str, str], category: str = "event"
    ) -> dict[str, str]:
        """
        翻译一组 key-value 数据，只翻译 value，key 作为上下文参考。

        Args:
            items: {key: value} 字典，key 提供给 LLM 作为参考，value 是待翻译内容
            category: 翻译类型，支持 event / profile / other，默认 event

        Returns:
            {key: translated_value} 字典
        """
        if category not in ("event", "profile", "other"):
            logger.warning("不支持的翻译类型: %s，使用默认 event", category)
            category = "event"

        if not items:
            return {}

        if not self.api_key:
            logger.error("未配置 API Key，无法翻译")
            return {k: v for k, v in items.items()}

        batches = self._split_batches(items)
        logger.info("翻译 %d 条，拆分为 %d 批", len(items), len(batches))

        results: dict[str, str] = {}
        for i, batch in enumerate(batches, 1):
            logger.info("翻译批次 %d/%d (%d 条)", i, len(batches), len(batch))
            batch_result = self._translate_batch(batch, category=category)
            results.update(batch_result)

        # 未成功翻译的保留原文
        for key, value in items.items():
            if key not in results:
                logger.warning("未翻译: %s -> %s", key, value)
                results[key] = value

        return results

    def _split_batches(self, items: dict[str, str]) -> list[dict[str, str]]:
        """按 MAX_BATCH_SIZE 拆分批次"""
        batches: list[dict[str, str]] = []
        current_batch: dict[str, str] = {}
        current_size = 0

        for key, value in items.items():
            line = f"{key}: {value}"
            line_size = len(line.encode("utf-8"))

            if current_batch and current_size + line_size > MAX_BATCH_SIZE:
                batches.append(current_batch)
                current_batch = {}
                current_size = 0

            current_batch[key] = value
            current_size += line_size

        if current_batch:
            batches.append(current_batch)

        return batches

    def _translate_batch(
        self, batch: dict[str, str], category: str = "event"
    ) -> dict[str, str]:
        """调用 LLM API 翻译一个批次"""
        lines = [f"{key}: {value}" for key, value in batch.items()]
        input_text = "\n".join(lines)

        base_prompt = (
            "你是专业的乒乓球领域中英翻译助手。\n"
            "输入格式为每行 \"key: value\"，key 是字段标识（供你参考上下文），value 是待翻译内容。\n"
            "请只翻译 value 部分为简体中文。\n\n"
        )

        if category == "event":
            rules_path = PROJECT_ROOT / "docs" / "rules" / "TRANSLATION_RULES.md"
            try:
                rules_content = rules_path.read_text(encoding="utf-8")
            except Exception:
                rules_content = ""
                logger.warning("未找到赛事翻译规则文件: %s", rules_path)

            if rules_content:
                system_prompt = (
                    base_prompt
                    + "请严格遵守以下赛事名称翻译规范：\n\n"
                    + rules_content
                    + "\n\n"
                    "输出格式：每行严格输出 \"key: 译文\"，保持 key 不变。\n"
                    "不要解释，不要序号，不要多余内容。"
                )
            else:
                system_prompt = (
                    base_prompt
                    + "如果是赛事，请把年份翻译在开头而不是结尾。\n\n"
                    "输出格式：每行严格输出 \"key: 译文\"，保持 key 不变。\n"
                    "不要解释，不要序号，不要多余内容。"
                )
        elif category == "profile":
            system_prompt = (
                base_prompt
                + "这是球员资料翻译，请使用标准中文体育术语和人名译名。\n\n"
                "输出格式：每行严格输出 \"key: 译文\"，保持 key 不变。\n"
                "不要解释，不要序号，不要多余内容。"
            )
        else:  # other
            system_prompt = (
                base_prompt
                + "输出格式：每行严格输出 \"key: 译文\"，保持 key 不变。\n"
                "不要解释，不要序号，不要多余内容。"
            )

        user_prompt = f"请翻译以下内容：\n\n{input_text}"

        response = self._call_api(system_prompt, user_prompt)
        if not response:
            return {}

        return self._parse_response(response, batch)

    def _call_api(self, system_prompt: str, user_prompt: str, max_retries: int = 3) -> str | None:
        """调用 MiniMax API，5xx 错误自动重试"""
        import time
        import urllib.error
        import urllib.request

        api_url = "https://api.minimax.chat/v1/text/chatcompletion_v2"

        data = json.dumps({
            "model": "MiniMax-M2.7",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }).encode("utf-8")

        for attempt in range(1, max_retries + 1):
            req = urllib.request.Request(
                api_url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode("utf-8"))

                    choices = result.get("choices")
                    if choices and len(choices) > 0:
                        return choices[0]["message"]["content"].strip()

                    reply = result.get("reply", "")
                    if reply:
                        return reply.strip()

                    base_resp = result.get("base_resp", {})
                    status_msg = base_resp.get("status_msg", "")
                    if status_msg:
                        logger.warning("API 返回错误: %s", status_msg)
                    else:
                        logger.warning("API 返回异常结构: %s", list(result.keys()))
                    return None

            except urllib.error.HTTPError as e:
                if e.code >= 500 and attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning("API %d 错误，%ds 后重试 (%d/%d)", e.code, wait, attempt, max_retries)
                    time.sleep(wait)
                    continue
                logger.error("API 调用失败: %s", e)
            except Exception as e:
                logger.error("API 调用失败: %s", e)

            return None

        return None

    def translate_document(self, content: str) -> str | None:
        """
        翻译整篇文档（如规则文档）。

        Args:
            content: 文档内容

        Returns:
            翻译后的中文文档，失败返回 None
        """
        if not self.api_key:
            logger.error("未配置 API Key，无法翻译文档")
            return None

        system_prompt = (
            "你是一个专业的体育文档翻译助手。\n"
            "请将以下ITTF相关文档翻译成中文。\n\n"
            "要求：\n"
            "1. 保持原有格式和结构（标题、段落、列表、表格）\n"
            "2. 人名使用标准中文译名\n"
            "3. 术语使用ITTF官方认可的中文术语\n"
            "4. 表格保持原样格式"
        )

        max_length = 6000
        if len(content) > max_length:
            logger.warning("文档较长(%d字符)，将截断至 %d", len(content), max_length)

        user_prompt = f"请翻译以下内容：\n\n{content[:max_length]}"
        return self._call_api(system_prompt, user_prompt)

    def _parse_response(self, response: str, batch: dict[str, str]) -> dict[str, str]:
        """解析 LLM 返回的 'key: 译文' 格式"""
        results: dict[str, str] = {}
        keys_set = set(batch.keys())

        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue

            sep_idx = line.find(": ")
            if sep_idx == -1:
                sep_idx = line.find(":")
                if sep_idx == -1:
                    continue

            key = line[:sep_idx].strip()
            value = line[sep_idx + 1:].strip().lstrip(" ")

            if key in keys_set and value:
                results[key] = value

        return results
