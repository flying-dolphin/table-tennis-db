"""
翻译常量模块

存放不能放在主词典中但翻译需要用到的词，这些词可能会和词典中的词产生冲突。
优先级高于主词典，翻译时优先查这里的常量。

例如：
- 月份简写 (Jan -> 一月)
- 数字月份 (01 -> 一月)
- 其他可能产生歧义的词
"""

from typing import TypedDict


class TranslationConstant(TypedDict):
    """常量翻译条目"""
    original: str
    translated: str
    category: str


MONTH_MAP: dict[str, TranslationConstant] = {
    # 月份英文缩写 -> 数字月份
    "jan": {"original": "Jan", "translated": "01", "category": "others"},
    "feb": {"original": "Feb", "translated": "02", "category": "others"},
    "mar": {"original": "Mar", "translated": "03", "category": "others"},
    "apr": {"original": "Apr", "translated": "04", "category": "others"},
    "may": {"original": "May", "translated": "05", "category": "others"},
    "jun": {"original": "Jun", "translated": "06", "category": "others"},
    "jul": {"original": "Jul", "translated": "07", "category": "others"},
    "aug": {"original": "Aug", "translated": "08", "category": "others"},
    "sep": {"original": "Sep", "translated": "09", "category": "others"},
    "oct": {"original": "Oct", "translated": "10", "category": "others"},
    "nov": {"original": "Nov", "translated": "11", "category": "others"},
    "dec": {"original": "Dec", "translated": "12", "category": "others"}
}


TRANSLATION_CONSTANTS: dict[str, TranslationConstant] = {
    **MONTH_MAP,
}


def lookup_constant(text: str) -> str | None:
    """
    查询常量翻译

    Args:
        text: 要查询的英文文本

    Returns:
        中文翻译或None（未命中）
    """
    key = text.strip().lower()
    entry = TRANSLATION_CONSTANTS.get(key)
    if entry:
        return entry["translated"]
    return None


def get_all_constants() -> dict[str, TranslationConstant]:
    """获取所有常量"""
    return TRANSLATION_CONSTANTS.copy()
