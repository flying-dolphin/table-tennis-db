#!/usr/bin/env python3
"""
通用翻译模块

功能：
- 维护中英文词典（人名、术语、赛事名）
- 优先查词典，未命中则调用LLM API翻译
- 自动将新翻译结果保存到词典
- 支持批量翻译和缓存
- 分词查词典 + 批量API翻译合并，减少API调用

支持的API：
- MiniMax（默认）
- 可扩展其他API

使用方法：
    from lib.translator import Translator

    translator = Translator(api_key="your_key")

    # 单条翻译
    cn_name = translator.translate("Zhang Jike", category="players")

    # 批量翻译（分词查词典 + 批量API）
    results = translator.translate_batch(
        ["Ma Long", "Fan Zhendong"],
        category="players"
    )
"""

from __future__ import annotations

import json
import os
import re
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

# 加载 .env 文件中的环境变量
from dotenv import load_dotenv

# 从项目根目录加载 .env
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# 默认词典路径
DEFAULT_DICT_PATH = Path(__file__).parent.parent / "data" / "translation_dict_v2.json"

# 词典分类
Category = Literal["players", "terms", "events", "locations", "others"]


class TranslationDict:
    """翻译词典管理器"""

    def __init__(self, dict_path: Path | str | None = None):
        self.dict_path = Path(dict_path) if dict_path else DEFAULT_DICT_PATH
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """加载词典文件"""
        if self.dict_path.exists():
            try:
                with open(self.dict_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                self._entries = self._normalize_entries(raw)
                logger.debug(f"已加载词典: {self.dict_path}")
            except Exception as e:
                logger.warning(f"加载词典失败: {e}，将创建新词典")
                self._entries = {}
        else:
            self._entries = {}
            self._save()  # 创建空词典文件

    def _save(self) -> None:
        """保存词典到文件"""
        try:
            self.dict_path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._serialize()
            with open(self.dict_path, 'w', encoding='utf-8', newline='') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.debug(f"词典已保存: {self.dict_path}")
        except Exception as e:
            logger.error(f"保存词典失败: {e}")

    def _source_priority(self, source: str) -> int:
        priorities = {"manual": 4, "dict": 3, "api": 2, "unknown": 1}
        return priorities.get((source or "unknown").lower(), 1)

    def _all_categories(self) -> list[str]:
        return ["players", "terms", "events", "locations", "others"]

    def _build_validators(self, categories: list[str]) -> dict[str, str]:
        validators: dict[str, str] = {}
        for category in categories:
            if category == "locations":
                validators[category] = "location"
            elif category == "players":
                validators[category] = "player_name"
            elif category == "events":
                validators[category] = "event_name"
            else:
                validators[category] = "none"
        return validators

    def _normalize_categories(self, categories: list[str]) -> list[str]:
        normalized = []
        for category in categories:
            if category not in self._all_categories():
                continue
            if category not in normalized:
                normalized.append(category)
        return sorted(normalized)

    def _normalize_key(self, text: str) -> str:
        return (text or "").strip().lower()

    def _normalize_entries(self, raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """只接受 V2 entries 结构。"""
        entries = raw.get("entries", {})
        if not isinstance(entries, dict):
            raise ValueError("词典必须为 V2 entries 结构")

        normalized: dict[str, dict[str, Any]] = {}
        for key, value in entries.items():
            if not isinstance(value, dict):
                continue
            normalized_key = self._normalize_key(key)
            if not normalized_key:
                continue
            categories = value.get("categories", [])
            if not isinstance(categories, list):
                categories = []
            categories = self._normalize_categories(categories)
            validators = value.get("validators")
            if not isinstance(validators, dict):
                raise ValueError(f"词条 {key} 缺少 validators")
            if any(category not in self._all_categories() for category in categories):
                raise ValueError(f"词条 {key} 包含未知 categories: {categories}")
            normalized[normalized_key] = {
                "original": (value.get("original") or key).strip(),
                "translated": (value.get("translated") or "").strip(),
                "categories": categories,
                "source": (value.get("source") or "unknown").strip().lower(),
                "review_status": (value.get("review_status") or "pending").strip().lower(),
                "validators": validators,
                "updated_at": (value.get("updated_at") or datetime.now().isoformat()).strip(),
            }
        return normalized

    def _serialize(self) -> dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "metadata": {
                "version": "2.0",
                "updated_at": now,
                "total_entries": len(self._entries),
            },
            "entries": self._entries,
        }

    def lookup(self, text: str, category: Category | None = None) -> str | None:
        """
        查询词典

        Args:
            text: 要查询的英文文本
            category: 指定分类查询，None则查询所有分类

        Returns:
            中文翻译或None（未命中）
        """
        text_normalized = self._normalize_key(text)
        entry = self._entries.get(text_normalized)
        if not entry:
            return None
        if category:
            if category not in entry.get("categories", []):
                if category == "locations":
                    fallback_entry = self._entries.get(text_normalized)
                    if fallback_entry and "others" in fallback_entry.get("categories", []):
                        return fallback_entry.get("translated")
                return None
        return entry.get("translated")

    def _upsert_entry(
        self,
        original: str,
        translated: str,
        category: Category,
        source: str,
    ) -> None:
        normalized = self._normalize_key(original)
        if not normalized:
            return
        now = datetime.now().isoformat()

        incoming_source = (source or "unknown").strip().lower()
        if normalized not in self._entries:
            self._entries[normalized] = {
                "original": original.strip(),
                "translated": translated.strip(),
                "categories": [category],
                "source": incoming_source,
                "review_status": "pending",
                "validators": self._build_validators([category]),
                "updated_at": now,
            }
            return

        entry = self._entries[normalized]
        categories = set(entry.get("categories", []))
        categories.add(category)
        entry["categories"] = sorted(categories)
        entry["validators"] = self._build_validators(entry["categories"])

        existing_source = str(entry.get("source", "unknown")).lower()
        should_replace = self._source_priority(incoming_source) >= self._source_priority(existing_source)
        if should_replace:
            entry["original"] = original.strip()
            entry["translated"] = translated.strip()
            entry["source"] = incoming_source
            entry["updated_at"] = now

    def add(
        self,
        original: str,
        translated: str,
        category: Category = "others",
        source: str = "api"
    ) -> None:
        """
        添加新词条到词典

        Args:
            original: 原文
            translated: 译文
            category: 分类
            source: 翻译来源 (dict/api/manual)
        """
        if category not in self._all_categories():
            category = "others"
        self._upsert_entry(original, translated, category, source)
        self._save()
        logger.debug(f"已添加词条 [{category}]: {original} -> {translated}")

    def add_many(
        self,
        entries: list[tuple[str, str, Category]],
        source: str = "api"
    ) -> None:
        """
        批量添加词条到词典（单次保存）

        Args:
            entries: [(原文, 译文, 分类), ...]
            source: 翻译来源
        """
        for original, translated, category in entries:
            if category not in self._all_categories():
                category = "others"
            self._upsert_entry(original, translated, category, source)

        self._save()
        logger.debug(f"批量添加 {len(entries)} 个词条")

    def get_stats(self) -> dict:
        """获取词典统计信息"""
        categories = self._all_categories()
        counts = {cat: 0 for cat in categories}
        for entry in self._entries.values():
            for cat in entry.get("categories", []):
                if cat in counts:
                    counts[cat] += 1
        total = sum(counts.values())
        return {
            "total": total,
            "players": counts["players"],
            "terms": counts["terms"],
            "events": counts["events"],
            "locations": counts["locations"],
            "others": counts["others"],
        }

    def dump(self) -> dict[str, Any]:
        """导出当前格式数据。"""
        return self._serialize()


class LLMTranslator:
    """LLM API 翻译器

    API Key 优先级：
    1. 传入的参数 api_key
    2. 环境变量 MINIMAX_API_KEY（从 .env 文件自动加载）
    """

    def __init__(self, api_key: str | None = None, provider: str = "minimax"):
        # 优先级：传入参数 > 环境变量（从 .env 加载）
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY")
        self.provider = provider.lower()

    @staticmethod
    def _build_batch_prompts(category: Category) -> tuple[str, str]:
        """按分类构建批量翻译提示词。"""
        prompt_by_category = {
            "players": (
                "你是专业乒乓球人名翻译助手。\n"
                "将英文运动员姓名翻译成标准中文译名。\n"
                "每行严格输出：原文|译文\n"
                "不要解释，不要序号。"
            ),
            "terms": (
                "你是专业乒乓球术语翻译助手。\n"
                "将英文术语翻译为中文体育术语。\n"
                "每行严格输出：原文|译文\n"
                "不要解释，不要序号。"
            ),
            "events": (
                "你是专业乒乓球赛事翻译助手。\n"
                "将英文赛事名称翻译为中文赛事名称。\n"
                "每行严格输出：原文|译文\n"
                "不要解释，不要序号。"
            ),
            "locations": (
                "你是地点名称翻译助手。\n"
                "输入可能是三位地区代码、国家名、城市名或其他地名。\n"
                "必须翻译成标准中文地名，不得翻译成赛事名、组织名或描述语。\n"
                "每行严格输出：原文|译文\n"
                "不要解释，不要序号。"
            ),
            "others": (
                "你是通用翻译助手。\n"
                "将输入翻译成简体中文。\n"
                "每行严格输出：原文|译文\n"
                "不要解释，不要序号。"
            ),
        }
        system_prompt = prompt_by_category.get(category, prompt_by_category["others"])
        user_prompt = (
            "请翻译以下内容：\n\n{texts}\n\n"
            "格式要求：\n"
            "1. 每行一个，格式为：原文|译文\n"
            "2. 只返回翻译结果，不要任何解释\n"
            "3. 保持原文完全一致，不要修改大小写或标点"
        )
        return system_prompt, user_prompt

    @staticmethod
    def _is_valid_location_translation(original: str, translated: str) -> bool:
        """地点翻译结果校验，过滤明显污染词条。"""
        if not translated:
            return False

        banned_tokens = ["WTT", "冠军赛", "公开赛", "挑战赛", "乒联", "联盟", "赛事", "锦标赛"]
        if any(token in translated for token in banned_tokens):
            return False

        # 常见国家代码场景下，不应保留英文大写代码本身
        is_code = bool(re.fullmatch(r"[A-Z]{3}", original.strip()))
        if is_code and translated.strip().upper() == original.strip().upper():
            return False

        return True

    def translate(
        self,
        text: str,
        context: str | None = None,
        category: Category = "others"
    ) -> str | None:
        """
        使用LLM API翻译单条文本

        Args:
            text: 要翻译的文本
            context: 上下文信息（帮助翻译更准确）
            category: 文本分类

        Returns:
            翻译结果或None（失败）
        """
        if not self.api_key:
            logger.warning("未配置API Key，跳过API翻译")
            return None

        if self.provider == "minimax":
            return self._translate_minimax(text, context, category)
        else:
            logger.error(f"不支持的翻译提供商: {self.provider}")
            return None

    def translate_batch_raw(
        self,
        texts: list[str],
        category: Category = "others"
    ) -> dict[str, str] | None:
        """
        批量调用 LLM API 翻译多条文本（原始结果，不查词典）

        Args:
            texts: 要翻译的文本列表
            category: 文本分类

        Returns:
            dict: {原文: 译文}，如果失败返回 None
        """
        if not texts:
            return {}

        if not self.api_key:
            logger.error("未配置 MiniMax API Key")
            return None

        return self._translate_minimax_batch(texts, category)

    def _translate_minimax(
        self,
        text: str,
        context: str | None,
        category: Category
    ) -> str | None:
        """使用MiniMax API翻译单条"""

        if not self.api_key:
            logger.error("MiniMax API Key 未配置")
            return None

        logger.debug(f"开始使用 MiniMax API 翻译: {text}")

        # 根据分类构建不同的提示词
        category_prompts = {
            "players": """请将以下乒乓球运动员的英文名翻译成中文人名。
要求：
1. 使用标准中文译名（如 Ma Long -> 马龙）
2. 如果是中文拼音，直接转换为对应的中文汉字
3. 保留姓氏和名字的结构
4. 只返回中文人名，不要解释""",
            "terms": """请将以下乒乓球术语翻译成中文。
要求：
1. 使用ITTF官方认可的中文术语
2. 保持专业性和准确性
3. 如果是表格、积分、排名相关术语，请使用体育/乒乓球领域标准译法
4. 只返回中文翻译，不要解释""",
            "events": """请将以下乒乓球赛事名称翻译成中文。
要求：
1. 使用官方中文赛事名称（如 World Championships -> 世界锦标赛）
2. 保留赛事级别信息（如 Grand Smash, WTT Series）
3. 只返回中文翻译，不要解释""",
            "locations": """请将以下地点代码、国家名、城市名或其他地名翻译成中文。
要求：
1. 使用标准中文地名或国家/地区名称
2. 如果是地点代码（如 CHN, JPN, TBD 以外的三位代码），请翻译为对应地名
3. 只返回中文，不要解释""",
            "others": """请将以下内容翻译成中文。
要求：
1. 如果是人名，使用标准中文译名。如果是国家简拼，使用标准中文国家名称
2. 如果是乒乓球术语，保持专业性
3. 只返回中文翻译，不要解释"""
        }

        system_prompt = category_prompts.get(category, category_prompts["others"])

        if context:
            user_prompt = f"上下文：{context}\n\n待翻译内容：{text}"
        else:
            user_prompt = f"待翻译内容：{text}"

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
                    'Authorization': f'Bearer {self.api_key}'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                response_body = response.read().decode('utf-8')
                result = json.loads(response_body)

                # 优先尝试标准 OpenAI 格式 (choices)
                choices = result.get('choices')
                if choices and len(choices) > 0:
                    translated = choices[0]['message']['content'].strip()
                    translated = translated.strip('"\'')
                    logger.debug(f"API翻译成功: {text} -> {translated}")
                    return translated

                # 备用：MiniMax 特有格式 (reply 字段)
                reply = result.get('reply', '')
                if reply:
                    translated = reply.strip()
                    translated = translated.strip('"\'')
                    logger.debug(f"API翻译成功(reply): {text} -> {translated}")
                    return translated

                # 检查错误信息
                base_resp = result.get('base_resp', {})
                status_msg = base_resp.get('status_msg', '')
                if status_msg:
                    logger.warning(f"API返回错误: {status_msg}")
                else:
                    logger.warning(f"API返回异常结构: {result}")

            return None

        except Exception as e:
            logger.error(f"MiniMax API调用失败: {e}")
            return None

    def _translate_minimax_batch(
        self,
        texts: list[str],
        category: Category
    ) -> dict[str, str] | None:
        """
        批量调用 MiniMax API 翻译多条文本

        Args:
            texts: 要翻译的文本列表
            category: 文本分类

        Returns:
            dict: {原文: 译文}，如果失败返回 None
        """
        if not texts:
            return {}

        if not self.api_key:
            logger.error("未配置 MiniMax API Key")
            return None

        items_text = "\n".join(texts)
        system_prompt, user_prompt_template = self._build_batch_prompts(category)
        user_prompt = user_prompt_template.format(texts=items_text)

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
                    'Authorization': f'Bearer {self.api_key}'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=120) as response:
                response_body = response.read().decode('utf-8')
                logger.debug(f"API 原始响应: {response_body[:500]}")

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
                                if category == "locations":
                                    if not self._is_valid_location_translation(original, translated):
                                        logger.warning(
                                            "丢弃可疑地点翻译: %s -> %s",
                                            original,
                                            translated,
                                        )
                                        continue
                                translations[original] = translated

                logger.info(f"批量翻译成功: 提交 {len(texts)} 条，解析出 {len(translations)} 条")
                return translations

        except Exception as e:
            logger.error(f"批量翻译 API 调用失败: {e}")
            return None


class Translator:
    """
    通用翻译器（词典 + API）

    使用示例：
        translator = Translator(api_key="your_key")

        # 翻译运动员名
        cn_name = translator.translate("Ma Long", category="players")

        # 翻译术语
        term = translator.translate("Round of 16", category="terms")

        # 批量翻译（分词查词典 + 批量API，节省token）
        names = ["Fan Zhendong", "Sun Yingsha", "Wang Chuqin"]
        results = translator.translate_batch(names, category="players")
    """

    def __init__(
        self,
        api_key: str | None = None,
        dict_path: Path | str | None = None,
        provider: str = "minimax",
        auto_save: bool = True
    ):
        """
        初始化翻译器

        Args:
            api_key: LLM API密钥（默认从MINIMAX_API_KEY环境变量读取）
            dict_path: 词典文件路径
            provider: API提供商（minimax）
            auto_save: 是否自动保存新词条到词典
        """
        self.dictionary = TranslationDict(dict_path)
        self.llm = LLMTranslator(api_key, provider)
        self.auto_save = auto_save
        self._cache: dict[str, str] = {}  # 运行时缓存

    def translate(
        self,
        text: str,
        category: Category = "others",
        context: str | None = None,
        use_api: bool = True
    ) -> str:
        """
        翻译单个文本

        Args:
            text: 要翻译的原文
            category: 文本分类（players/terms/events/locations/others）
            context: 上下文信息，帮助API更准确翻译
            use_api: 词典未命中时是否调用API

        Returns:
            中文翻译（如果失败则返回原文）
        """
        if not text or not isinstance(text, str):
            return text

        text = text.strip()
        if not text:
            return text

        # 检查运行时缓存
        cache_key = f"{category}:{text.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 检查词典
        result = self.dictionary.lookup(text, category)
        if result:
            self._cache[cache_key] = result
            return result

        # 未命中，调用API
        if use_api:
            api_result = self.llm.translate(text, context, category)
            if api_result:
                # 保存到词典
                if self.auto_save:
                    self.dictionary.add(text, api_result, category, source="api")
                self._cache[cache_key] = api_result
                return api_result

        # 翻译失败，返回原文
        return text

    def _word_lookup(self, text: str, category: Category) -> tuple[dict[str, str], list[str], list[str]]:
        """
        分词查词典

        Args:
            text: 原文
            category: 分类

        Returns:
            (known_dict, known_words, unknown_words)
            known_dict: {原词: 译文}
            known_words: 原词列表（已有翻译）
            unknown_words: 原词列表（无翻译）
        """
        words = text.strip().split()
        known_dict = {}
        known_words = []
        unknown_words = []

        for w in words:
            w_lower = w.strip().lower()
            if not w_lower:
                continue
            translation = self.dictionary.lookup(w, category)
            if translation:
                known_dict[w_lower] = translation
                known_words.append(w)
            else:
                unknown_words.append(w)

        return known_dict, known_words, unknown_words

    def translate_batch(
        self,
        texts: list[str],
        category: Category = "others",
        context: str | None = None,
        use_api: bool = True
    ) -> dict[str, str]:
        """
        批量翻译（分词查词典 + 批量API）

        流程：
        1. 对每条文本按空格分词，逐个查词典
        2. 收集所有未知词（单词）和完整文本分开处理：
           - 单词：批量API翻译 → 存入 new_word_translations → 存入词典
           - 完整文本：批量API翻译 → 存入 full_text_results
        3. 组装时优先用完整文本翻译，单词翻译作为降级
        4. 完整文本翻译结果存入词典

        Args:
            texts: 要翻译的文本列表
            category: 文本分类
            context: 上下文信息（帮助翻译更准确）
            use_api: 是否使用API翻译未命中的词条

        Returns:
            dict: {原文: 译文}
        """
        results = {}

        # 快速路径：全部文本已在缓存/词典中
        cache_hits = {}
        texts_to_api = []

        for text in texts:
            text = text.strip()
            if not text:
                results[text] = ""
                continue

            cache_key = f"{category}:{text.lower()}"
            if cache_key in self._cache:
                cache_hits[text] = self._cache[cache_key]
                continue

            dict_result = self.dictionary.lookup(text, category)
            if dict_result:
                self._cache[cache_key] = dict_result
                cache_hits[text] = dict_result
                continue

            texts_to_api.append(text)

        # 全部命中缓存/词典
        if not texts_to_api:
            results.update(cache_hits)
            logger.info(f"批量翻译: 全部 {len(cache_hits)} 条命中缓存/词典")
            return results

        logger.info(f"批量翻译: 命中 {len(cache_hits)}/{len(texts)} 条，API翻译 {len(texts_to_api)} 条")

        # ---- 分词查词典 + 批量API ----
        # 区分：单词（1个词）vs 完整文本（多个词）
        single_words: list[str] = []      # 未知单词，逐个调API
        multi_texts: list[str] = []       # 多词文本，批量调API
        texts_word_info: dict[str, tuple[dict[str, str], list[str], list[str]]] = {}

        for text in texts_to_api:
            known_dict, known_words, unknown_words = self._word_lookup(text, category)
            texts_word_info[text] = (known_dict, known_words, unknown_words)

            if len(text.split()) == 1:
                # 单词，单独调API
                single_words.append(text)
            else:
                multi_texts.append(text)

        logger.info(f"  分词查词典: {len(single_words)} 个单词 + {len(multi_texts)} 个多词文本")

        # 单词批量API翻译 → new_word_translations
        new_word_translations: dict[str, str] = {}
        if single_words and use_api:
            word_batch = self.llm.translate_batch_raw(single_words, category)
            if word_batch:
                new_word_translations.update(word_batch)
                # 新单词存入词典
                new_entries = [
                    (w, new_word_translations[w], category)
                    for w in single_words
                    if w in new_word_translations
                ]
                if new_entries and self.auto_save:
                    self.dictionary.add_many(new_entries, source="api")
                logger.info(f"  单词翻译: {len(new_word_translations)}/{len(single_words)} 条有结果")
            else:
                logger.warning(f"  单词批量API翻译失败")

        # 多词文本批量API翻译 → full_text_results
        full_text_results: dict[str, str] = {}
        if multi_texts and use_api:
            for i in range(0, len(multi_texts), 20):
                batch = multi_texts[i:i + 20]
                batch_result = self.llm.translate_batch_raw(batch, category)
                if batch_result:
                    full_text_results.update(batch_result)
                else:
                    # 降级：逐条翻译
                    for text in batch:
                        single = self.llm.translate(text, context, category)
                        if single:
                            full_text_results[text] = single
                time.sleep(0.5)
            logger.info(f"  完整文本翻译: {len(full_text_results)}/{len(multi_texts)} 条有结果")

        # 组装最终结果
        new_full_text_entries: list[tuple[str, str, Category]] = []

        for text in texts_to_api:
            known_dict, known_words, unknown_words = texts_word_info[text]
            words = text.split()

            if len(words) == 1:
                # 单词：直接用 API 结果（new_word_translations）
                if text in new_word_translations:
                    translated = new_word_translations[text]
                else:
                    translated = text
            elif text in full_text_results:
                # 多词文本：优先用完整翻译（API 考虑了完整语境，结果最准确）
                translated = full_text_results[text]
            elif not unknown_words:
                # 多词但无未知词 → 全部已知词组合
                translated = "".join(known_dict.get(w.lower(), w) for w in words)
            else:
                # 部分未知词且无完整翻译 → 混用已知词 + 单词翻译（最后降级）
                translated_parts = []
                for w in words:
                    w_lower = w.lower()
                    if w_lower in known_dict:
                        translated_parts.append(known_dict[w_lower])
                    elif w in new_word_translations:
                        translated_parts.append(new_word_translations[w])
                    else:
                        translated_parts.append(w)
                translated = "".join(translated_parts)

            results[text] = translated
            cache_key = f"{category}:{text.lower()}"
            self._cache[cache_key] = translated

            # 完整文本新词条
            if self.auto_save and translated != text and text not in [kv[0] for kv in new_full_text_entries]:
                new_full_text_entries.append((text, translated, category))

        # 存完整文本翻译到词典
        if new_full_text_entries:
            self.dictionary.add_many(new_full_text_entries, source="api")
            logger.info(f"  新增完整文本词条: {len(new_full_text_entries)}")

        results.update(cache_hits)
        return results

    def translate_document(
        self,
        content: str,
        doc_type: str = "general"
    ) -> str:
        """
        翻译完整文档（如规则文档）

        Args:
            content: 文档内容
            doc_type: 文档类型（general/regulations/match_report）

        Returns:
            翻译后的中文文档
        """
        # 文档翻译直接走API，不经过词典
        if not self.llm.api_key:
            logger.warning("未配置API Key，无法翻译文档")
            return content

        system_prompt = """你是一个专业的体育文档翻译助手。
请将以下ITTF相关文档翻译成中文。

要求：
1. 保持原有格式和结构（标题、段落、列表、表格）
2. 人名使用标准中文译名
3. 术语使用ITTF官方认可的中文术语
4. 表格保持原样格式
5. 添加页脚说明（文件来源、翻译日期）"""

        try:
            import urllib.request

            # 分段处理长文档
            max_length = 6000
            if len(content) > max_length:
                logger.warning(f"文档较长({len(content)}字符)，将分段翻译")

            # MiniMax 标准 API 端点
            api_url = 'https://api.minimax.chat/v1/text/chatcompletion_v2'

            data = json.dumps({
                "model": "MiniMax-M2.7",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请翻译以下内容：\n\n{content[:max_length]}"}
                ],
                "temperature": 0.1
            }).encode('utf-8')

            req = urllib.request.Request(
                api_url,
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.llm.api_key}'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))

                # 优先尝试标准 OpenAI 格式
                choices = result.get('choices')
                if choices and len(choices) > 0:
                    return choices[0]['message']['content'].strip()

                # 备用：MiniMax 特有格式
                reply = result.get('reply', '')
                if reply:
                    return reply.strip()

            return content

        except Exception as e:
            logger.error(f"文档翻译失败: {e}")
            return content

    def add_manual_translation(
        self,
        original: str,
        translated: str,
        category: Category = "others"
    ) -> None:
        """
        手动添加翻译词条（用于人工校对后的结果）

        Args:
            original: 原文
            translated: 译文
            category: 分类
        """
        self.dictionary.add(original, translated, category, source="manual")
        cache_key = f"{category}:{original.lower()}"
        self._cache[cache_key] = translated

    def get_stats(self) -> dict:
        """获取词典统计信息"""
        return self.dictionary.get_stats()

    def export_dict(self, output_path: Path | str) -> None:
        """导出词典到指定路径"""
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                json.dump(self.dictionary.dump(), f, ensure_ascii=False, indent=2)
            logger.info(f"词典已导出: {output_path}")
        except Exception as e:
            logger.error(f"导出词典失败: {e}")


# 便捷函数：快速翻译（使用默认配置）
def quick_translate(
    text: str,
    category: Category = "others",
    api_key: str | None = None
) -> str:
    """
    快速翻译函数（使用默认配置）

    Args:
        text: 要翻译的文本
        category: 分类
        api_key: API密钥（默认从环境变量读取）

    Returns:
        中文翻译
    """
    translator = Translator(api_key=api_key)
    return translator.translate(text, category)


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)

    translator = Translator()
    print(f"词典统计: {translator.get_stats()}")

    # 测试翻译
    test_names = ["Ma Long", "Fan Zhendong", "Test Player XYZ"]
    for name in test_names:
        result = translator.translate(name, category="players")
        print(f"{name} -> {result}")
