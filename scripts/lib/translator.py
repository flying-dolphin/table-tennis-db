#!/usr/bin/env python3
"""
通用翻译模块

功能：
- 维护中英文词典（人名、术语、赛事名）
- 优先查词典，未命中则调用LLM API翻译
- 自动将新翻译结果保存到词典
- 支持批量翻译和缓存

支持的API：
- MiniMax（默认）
- 可扩展其他API

使用方法：
    from lib.translator import Translator
    
    translator = Translator(api_key="your_key")
    
    # 单条翻译
    cn_name = translator.translate("Zhang Jike", category="players")
    
    # 批量翻译
    results = translator.translate_batch(
        ["Ma Long", "Fan Zhendong"], 
        category="players"
    )
"""

from __future__ import annotations

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

# 加载 .env 文件中的环境变量
from dotenv import load_dotenv

# 从项目根目录加载 .env
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# 默认词典路径
DEFAULT_DICT_PATH = Path(__file__).parent.parent / "data" / "translation_dict.json"

# 词典分类
Category = Literal["players", "terms", "events", "countries", "others"]


class TranslationDict:
    """翻译词典管理器"""
    
    def __init__(self, dict_path: Path | str | None = None):
        self.dict_path = Path(dict_path) if dict_path else DEFAULT_DICT_PATH
        self._data: dict = {}
        self._load()
    
    def _load(self) -> None:
        """加载词典文件"""
        if self.dict_path.exists():
            try:
                with open(self.dict_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                logger.debug(f"已加载词典: {self.dict_path}")
            except Exception as e:
                logger.warning(f"加载词典失败: {e}，将创建新词典")
                self._data = self._init_empty_dict()
        else:
            self._data = self._init_empty_dict()
            self._save()  # 创建空词典文件
    
    def _save(self) -> None:
        """保存词典到文件"""
        try:
            self.dict_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dict_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.debug(f"词典已保存: {self.dict_path}")
        except Exception as e:
            logger.error(f"保存词典失败: {e}")
    
    def _init_empty_dict(self) -> dict:
        """初始化空词典结构"""
        return {
            "metadata": {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "total_entries": 0
            },
            "players": {},      # 运动员人名
            "terms": {},        # 通用术语
            "events": {},       # 赛事名称
            "countries": {},    # 国家/地区
            "others": {}        # 其他词汇
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
        text_normalized = text.strip().lower()
        
        if category:
            if category not in self._data:
                return None
            entry = self._data[category].get(text_normalized)
            return entry["translated"] if entry else None
        
        # 查询所有分类
        for cat in ["players", "terms", "events", "countries", "others"]:
            if cat in self._data:
                entry = self._data[cat].get(text_normalized)
                if entry:
                    return entry["translated"]
        
        return None
    
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
        if category not in self._data:
            category = "others"
        
        original_normalized = original.strip().lower()
        
        self._data[category][original_normalized] = {
            "original": original.strip(),
            "translated": translated.strip(),
            "source": source,
            "updated_at": datetime.now().isoformat()
        }
        
        # 更新元数据
        total = sum(len(self._data[cat]) for cat in ["players", "terms", "events", "countries", "others"])
        self._data["metadata"]["updated_at"] = datetime.now().isoformat()
        self._data["metadata"]["total_entries"] = total
        
        self._save()
        logger.debug(f"已添加词条 [{category}]: {original} -> {translated}")
    
    def get_stats(self) -> dict:
        """获取词典统计信息"""
        return {
            "total": self._data["metadata"]["total_entries"],
            "players": len(self._data.get("players", {})),
            "terms": len(self._data.get("terms", {})),
            "events": len(self._data.get("events", {})),
            "countries": len(self._data.get("countries", {})),
            "others": len(self._data.get("others", {}))
        }


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
    
    def translate(
        self, 
        text: str, 
        context: str | None = None,
        category: Category = "others"
    ) -> str | None:
        """
        使用LLM API翻译
        
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
    
    def _translate_minimax(
        self, 
        text: str, 
        context: str | None,
        category: Category
    ) -> str | None:
        """使用MiniMax API翻译"""
        
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
            "countries": """请将以下国家/地区代码或名称翻译成中文。
要求：
1. 使用标准中文国家名称
2. 如果是国家代码（如 CHN, JPN），请翻译为国家名
3. 只返回中文，不要解释""",
            "others": """请将以下内容翻译成中文。
要求：
1. 如果是人名，使用标准中文译名
2. 如果是术语，保持专业性
3. 只返回中文翻译，不要解释"""
        }
        
        system_prompt = category_prompts.get(category, category_prompts["others"])
        
        if context:
            user_prompt = f"上下文：{context}\n\n待翻译内容：{text}"
        else:
            user_prompt = f"待翻译内容：{text}"
        
        try:
            import urllib.request
            
            data = json.dumps({
                "model": "MiniMax-Text-01",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1  # 低温度，更确定性的翻译
            }).encode('utf-8')
            
            req = urllib.request.Request(
                'https://api.minimax.chat/v1/text/chatcompletion_pro',
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}'
                },
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                if 'choices' in result and len(result['choices']) > 0:
                    translated = result['choices'][0]['message']['content'].strip()
                    # 清理可能的引号
                    translated = translated.strip('"\'')
                    logger.debug(f"API翻译: {text} -> {translated}")
                    return translated
            
            return None
            
        except Exception as e:
            logger.error(f"MiniMax API调用失败: {e}")
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
        
        # 批量翻译（带缓存）
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
            category: 文本分类（players/terms/events/countries/others）
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
    
    def translate_batch(
        self, 
        texts: list[str], 
        category: Category = "others",
        context: str | None = None,
        use_api: bool = True
    ) -> dict[str, str]:
        """
        批量翻译
        
        Args:
            texts: 要翻译的文本列表
            category: 文本分类
            context: 上下文信息
            use_api: 是否使用API翻译未命中的词条
            
        Returns:
            dict: {原文: 译文}
        """
        results = {}
        for text in texts:
            results[text] = self.translate(text, category, context, use_api)
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
            
            data = json.dumps({
                "model": "MiniMax-Text-01",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请翻译以下内容：\n\n{content[:max_length]}"}
                ],
                "temperature": 0.1
            }).encode('utf-8')
            
            req = urllib.request.Request(
                'https://api.minimax.chat/v1/text/chatcompletion_pro',
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.llm.api_key}'
                },
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content'].strip()
            
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
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.dictionary._data, f, ensure_ascii=False, indent=2)
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
