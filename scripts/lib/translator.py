#!/usr/bin/env python3
"""
纯 LLM 翻译模块

功能：
- 接收 dict[str, str] (key -> value)，只翻译 value，key 作为上下文参考
- 自动按大小拆分批次提交 LLM
- 返回 dict[str, str] (key -> translated_value)

支持的 API：
- MiniMax（默认）：provider="minimax"
- Kimi（Moonshot AI）：provider="kimi"
- 通义千问（阿里云）：provider="qwen"

使用方法：
    from lib.translator import LLMTranslator

    translator = LLMTranslator()  # 默认 MiniMax
    translator = LLMTranslator(provider="kimi", model="moonshot-v1-32k")
    translator = LLMTranslator(provider="qwen", model="qwen-plus")
    results = translator.translate({"Ma Long": "Ma Long", "event_name": "World Championships"})
    # => {"Ma Long": "马龙", "event_name": "世界锦标赛"}
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from queue import Empty, Queue
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

try:
    from .dict_translator import DictTranslator
except ImportError:
    from lib.dict_translator import DictTranslator

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 10240 # 单批次最大字符数


class LLMTranslator:
    """纯 LLM 翻译器

    支持的 provider：
    - minimax：API Key 来自环境变量 MINIMAX_API_KEY
    - kimi：API Key 来自环境变量 MOONSHOT_API_KEY
    - qwen：API Key 来自环境变量 DASHSCOPE_API_KEY

    API Key 优先级：
    1. 传入的参数 api_key
    2. 对应 provider 的环境变量（从 .env 文件自动加载）
    """

    PROVIDER_CONFIGS: dict[str, dict] = {
        "minimax": {
            "api_url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
            "default_model": "MiniMax-M2.7",
            "env_key": "MINIMAX_API_KEY",
        },
        "kimi": {
            "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "default_model": "kimi-k2.5",
            "env_key": "KIMI_API_KEY",
        },
        "qwen": {
            "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "default_model": "qwen3.5-plus",
            "env_key": "DASHSCOPE_API_KEY",
            "request_timeout": 240,
            "max_batch_size": 4096,
        },
        "glm": {
            "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "default_model": "glm-5",
            "env_key": "ZHIPU_API_KEY",
            "request_timeout": 180,
        },
        "deepseek": {
            "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "default_model": "deepseek-v3.2",
            "env_key": "DEEPSEEK_API_KEY",
            "request_timeout": 180,
        },
    }

    def __init__(
        self,
        api_key: str | None = None,
        provider: str = "minimax",
        model: str | None = None,
    ):
        self.provider = provider.lower()
        if self.provider not in self.PROVIDER_CONFIGS:
            supported = ", ".join(self.PROVIDER_CONFIGS.keys())
            raise ValueError(f"不支持的 provider: {provider}，支持: {supported}")

        cfg = self.PROVIDER_CONFIGS[self.provider]
        self.api_key = api_key or os.environ.get(cfg["env_key"])
        self.model = model or cfg["default_model"]
        self._api_url = cfg["api_url"]
        self._request_timeout = int(cfg.get("request_timeout", 120))
        self._max_batch_size = int(cfg.get("max_batch_size", MAX_BATCH_SIZE))
        self.total_tokens: dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}
        self._dict_translator = DictTranslator()

    def translate(
        self,
        items: dict[str, str],
        category: str = "event",
        on_batch_complete: Callable[[int, int, dict[str, str]], None] | None = None,
    ) -> dict[str, str] | None:
        """
        翻译一组 key-value 数据，只翻译 value，key 作为上下文参考。

        Args:
            items: {key: value} 字典，key 提供给 LLM 作为参考，value 是待翻译内容
            category: 翻译类型，支持 event / profile / other，默认 event

        Returns:
            {key: translated_value} 字典，翻译完全失败时返回 None
        """
        if category not in ("event", "profile", "other"):
            logger.warning("不支持的翻译类型: %s，使用默认 event", category)
            category = "event"

        if not items:
            return {}

        dict_results, llm_items = self._split_dict_hits(items, category)
        if dict_results:
            logger.info("词典命中 %d 条，剩余 %d 条走 LLM", len(dict_results), len(llm_items))

        if not llm_items:
            if on_batch_complete is not None and dict_results:
                on_batch_complete(1, 1, dict(dict_results))
            return self._merge_results(items, dict_results, {})

        if not self.api_key:
            logger.error("未配置 API Key，无法翻译剩余 %d 条内容", len(llm_items))
            return None

        batches = self._split_batches(llm_items)
        total_batches = len(batches) + (1 if dict_results else 0)
        logger.info(
            "翻译 %d 条，拆分为 %d 批 [%s %s, batch_limit=%d, timeout=%ss]",
            len(llm_items), len(batches), self.provider, self.model, self._max_batch_size, self._request_timeout
        )

        llm_results: dict[str, str] = {}
        if on_batch_complete is not None and dict_results:
            on_batch_complete(1, total_batches, dict(dict_results))

        batch_offset = 1 if dict_results else 0
        for i, batch in enumerate(batches, 1):
            logger.info("翻译批次 %d/%d (%d 条)", i, len(batches), len(batch))
            batch_result = self._translate_batch(batch, category=category)
            if not batch_result:
                logger.error("批次 %d/%d 翻译失败", i, len(batches))
                return None
            llm_results.update(batch_result)
            if on_batch_complete is not None:
                on_batch_complete(i + batch_offset, total_batches, dict(batch_result))

        results = self._merge_results(items, dict_results, llm_results)

        if self.total_tokens["total"]:
            logger.info(
                "Token 累计 [%s %s]: prompt=%d, completion=%d, total=%d",
                self.provider, self.model,
                self.total_tokens["prompt"],
                self.total_tokens["completion"],
                self.total_tokens["total"],
            )

        return results

    def _split_dict_hits(self, items: dict[str, str], category: str) -> tuple[dict[str, str], dict[str, str]]:
        dict_results: dict[str, str] = {}
        llm_items: dict[str, str] = {}

        for key, value in items.items():
            dict_category = self._resolve_dict_category(key, category)
            translated = self._dict_translator.translate(value, dict_category) if dict_category else None
            if translated is not None and translated != value:
                dict_results[key] = translated
            else:
                llm_items[key] = value

        return dict_results, llm_items

    def _resolve_dict_category(self, key: str, category: str) -> str | None:
        if category == "event":
            return "events"

        if category == "profile":
            field = key.rsplit(".", 1)[-1].lower()
            if field == "name":
                return "players"
            if field == "country":
                return "locations"
            if field in {"gender", "style", "playing_hand", "grip"}:
                return "terms_others"
            return None

        if category == "other":
            return "terms_others"

        return None

    def _merge_results(
        self,
        items: dict[str, str],
        dict_results: dict[str, str],
        llm_results: dict[str, str],
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        for key, value in items.items():
            if key in dict_results:
                merged[key] = dict_results[key]
            elif key in llm_results:
                merged[key] = llm_results[key]
            else:
                logger.warning("未翻译: %s -> %s", key, value)
                merged[key] = value
        return merged

    def _split_batches(self, items: dict[str, str]) -> list[dict[str, str]]:
        """按 provider 对应的批次大小拆分批次"""
        batches: list[dict[str, str]] = []
        current_batch: dict[str, str] = {}
        current_size = 0

        for key, value in items.items():
            line = f"{key}: {value}"
            line_size = len(line.encode("utf-8"))

            if current_batch and current_size + line_size > self._max_batch_size:
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
        batch_bytes = len(input_text.encode("utf-8"))

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

        logger.info(
            "提交翻译批次 [%s %s]: items=%d, input_bytes=%d",
            self.provider, self.model, len(batch), batch_bytes
        )
        response = self._call_api(system_prompt, user_prompt)
        if not response:
            return {}

        return self._parse_response(response, batch)

    def _call_api(self, system_prompt: str, user_prompt: str, max_retries: int = 3) -> str | None:
        """调用 LLM API，5xx 错误自动重试。支持 minimax / kimi / qwen。"""
        import time
        import urllib.error
        import urllib.request

        data = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }).encode("utf-8")

        for attempt in range(1, max_retries + 1):
            req = urllib.request.Request(
                self._api_url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )

            try:
                result = self._urlopen_json_interruptible(req, timeout=self._request_timeout)

                choices = result.get("choices")
                if choices and len(choices) > 0:
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
                    if total_tokens:
                        self.total_tokens["prompt"] += prompt_tokens
                        self.total_tokens["completion"] += completion_tokens
                        self.total_tokens["total"] += total_tokens
                        logger.info(
                            "Token 消耗 [%s %s]: prompt=%d, completion=%d, total=%d",
                            self.provider, self.model,
                            prompt_tokens, completion_tokens, total_tokens,
                        )
                    return choices[0]["message"]["content"].strip()

                # MiniMax 旧版兼容字段
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

            except KeyboardInterrupt:
                logger.warning("API 调用被用户中断")
                raise
            except urllib.error.HTTPError as e:
                if e.code >= 500 and attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning("API %d 错误，%ds 后重试 (%d/%d)", e.code, wait, attempt, max_retries)
                    time.sleep(wait)
                    continue
                logger.error("API 调用失败 [%s %s]: %s", self.provider, self.model, e)
            except urllib.error.URLError as e:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning("API 网络错误，%ds 后重试 (%d/%d): %s", wait, attempt, max_retries, e.reason)
                    time.sleep(wait)
                    continue
                logger.error("API 调用失败 [%s %s]: %s", self.provider, self.model, e)
            except (socket.timeout, TimeoutError) as e:
                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "API 读取超时，%ds 后重试 (%d/%d) [%s %s, timeout=%ss]: %s",
                        wait, attempt, max_retries, self.provider, self.model, self._request_timeout, e
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    "API 调用失败 [%s %s]: read timeout after %ss: %s",
                    self.provider, self.model, self._request_timeout, e
                )
            except Exception as e:
                logger.error("API 调用失败 [%s %s]: %s", self.provider, self.model, e)

            return None

        return None

    def _urlopen_json_interruptible(self, req, timeout: int = 120) -> dict:
        """在后台线程执行 urlopen，让主线程可及时响应 Ctrl+C。"""
        result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)

        def worker() -> None:
            import urllib.request

            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = resp.read().decode("utf-8")
                result_queue.put(("ok", json.loads(payload)))
            except BaseException as exc:
                result_queue.put(("err", exc))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            try:
                status, payload = result_queue.get(timeout=0.5)
            except Empty:
                continue

            if status == "ok":
                return payload  # type: ignore[return-value]
            raise payload  # type: ignore[misc]

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
