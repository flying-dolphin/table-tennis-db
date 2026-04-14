#!/usr/bin/env python3
"""
ITTF 排名规则文件管理器

功能：
- 从 ITTF 官网获取最新排名规则 PDF（调用 scrape_regulations 模块）
- 将 PDF 转换为 Markdown 格式
- 翻译成中文（支持 MiniMax API 或生成翻译提示）
- 状态管理，避免重复处理
- 支持守护进程模式，定期检查更新

使用方法：
    python regulations_manager.py              # 运行一次检查
    python regulations_manager.py --force      # 强制重新处理所有文件
    python regulations_manager.py --daemon     # 持续运行，每3天检查一次
    python regulations_manager.py --translate  # 仅翻译已有PDF
    python regulations_manager.py --headless   # 使用 headless 模式抓取

依赖：
    pip install requests pypdf beautifulsoup4
"""

from __future__ import annotations

import os
import sys
import time
import hashlib
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

# 导入抓取模块
sys.path.insert(0, str(Path(__file__).parent))
from scrape_regulations import fetch_regulations, RANKINGS_URL
from lib.translator import Translator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 路径配置
SCRIPT_DIR = Path(__file__).parent
DOCS_DIR = SCRIPT_DIR.parent / "docs"
DATA_DIR = SCRIPT_DIR.parent / "data"
STATE_FILE = SCRIPT_DIR / ".regulations_manager_state.json"

# 检查间隔（秒）- 3天
CHECK_INTERVAL = 3 * 24 * 60 * 60


def get_file_hash(file_path: Path) -> str:
    """计算文件MD5哈希"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_state():
    """加载上次运行状态"""
    import json
    
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载状态文件失败: {e}")
    
    return {
        'last_check': None,
        'last_pdf_hash': None,
        'last_pdf_name': None,
        'versions_processed': []
    }


def save_state(state):
    """保存运行状态"""
    import json
    
    with open(STATE_FILE, 'w', encoding='utf-8', newline='') as f:
        json.dump(state, f, indent=2)


def find_local_pdfs():
    """查找本地已有的PDF文件"""
    pdfs = {}
    if DOCS_DIR.exists():
        for f in DOCS_DIR.glob("*.pdf"):
            pdfs[f.name] = f
    return pdfs


def translate_document_with_translator(
    md_path: Path, 
    cn_path: Path, 
    use_api: bool = False, 
    api_key: str | None = None
) -> bool:
    """使用翻译模块将英文Markdown翻译成中文
    
    Args:
        md_path: 英文Markdown文件路径
        cn_path: 中文输出文件路径
        use_api: 是否使用API进行翻译
        api_key: MiniMax API密钥（如果使用API）
    """
    logger.info(f"正在翻译: {md_path}")
    
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if use_api and api_key:
            # 使用翻译模块进行文档翻译
            logger.info("使用MiniMax API翻译...")
            translator = Translator(api_key=api_key)
            translated = translator.translate_document(content, doc_type="regulations")
            
            if translated and translated != content:
                with open(cn_path, 'w', encoding='utf-8', newline='') as f:
                    f.write(translated)
                logger.info(f"中文文档已保存: {cn_path}")
                
                # 显示词典统计
                stats = translator.get_stats()
                logger.info(f"词典统计: 共 {stats['total']} 个词条")
                return True
            else:
                logger.warning("API翻译失败，保存翻译提示")
        
        # 保存翻译提示供后续处理
        translation_prompt = f"""请将以下ITTF世界乒乓球排名规则的英文文档翻译成中文。

要求：
1. 保持原有格式和结构
2. 准确翻译专业术语
3. 表格保持原样
4. 添加页脚说明（文件来源、最后更新日期、原文链接）

以下是文档内容：

{content}"""
        
        prompt_path = md_path.with_suffix('.translation_prompt.txt')
        with open(prompt_path, 'w', encoding='utf-8', newline='') as f:
            f.write(translation_prompt)
        
        logger.info(f"翻译提示已保存到: {prompt_path}")
        return True
        
    except Exception as e:
        logger.error(f"翻译准备失败: {e}")
        return False


def process_pdf(pdf_path: Path, force: bool = False, use_api: bool = False, api_key: str | None = None):
    """处理单个PDF文件
    
    Args:
        pdf_path: PDF文件路径
        force: 是否强制重新处理
        use_api: 是否使用API翻译
        api_key: API密钥
    """
    logger.info(f"处理PDF: {pdf_path}")
    
    # 计算哈希
    pdf_hash = get_file_hash(pdf_path)
    pdf_name = pdf_path.name
    
    # 检查是否已处理过
    state = load_state()
    if not force and pdf_hash == state.get('last_pdf_hash'):
        logger.info("PDF未变化，跳过处理")
        return False
    
    # 提取日期信息
    date_match = None
    import re
    for pattern in [r'(\d{8})', r'(\d{4}-\d{2}-\d{2})', r'(\d{4})(\d{2})(\d{2})']:
        match = re.search(pattern, pdf_name)
        if match:
            date_match = ''.join(match.groups())
            break
    
    # 生成输出文件名
    if date_match:
        base_name = f"ITTF-Ranking-Regulations-{date_match}"
    else:
        base_name = f"ITTF-Ranking-Regulations-{datetime.now().strftime('%Y%m%d')}"
    
    md_path = DOCS_DIR / f"{base_name}.md"
    cn_path = DOCS_DIR / f"{base_name}-CN.md"
    
    # 如果 markdown 已存在，直接使用
    if md_path.exists() and not force:
        logger.info(f"Markdown已存在: {md_path}")
    else:
        # 需要从 PDF 提取
        try:
            import pypdf
            logger.info(f"正在提取PDF内容: {pdf_path}")
            reader = pypdf.PdfReader(pdf_path)
            num_pages = len(reader.pages)
            logger.info(f"PDF共 {num_pages} 页")
            
            full_text = ""
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    full_text += f"\n\n## 第 {i+1} 页\n\n{page_text}"
            
            with open(md_path, 'w', encoding='utf-8', newline='') as f:
                f.write(full_text)
            
            logger.info(f"已提取文本到: {md_path}")
        except Exception as e:
            logger.error(f"PDF提取失败: {e}")
            return False
    
    # 翻译
    translate_document_with_translator(md_path, cn_path, use_api=use_api, api_key=api_key)
    
    # 更新状态
    state['last_check'] = datetime.now().isoformat()
    state['last_pdf_hash'] = pdf_hash
    state['last_pdf_name'] = pdf_name
    if pdf_name not in state['versions_processed']:
        state['versions_processed'].append(pdf_name)
    save_state(state)
    
    logger.info(f"✅ 处理完成!")
    logger.info(f"   英文文档: {md_path}")
    logger.info(f"   中文文档: {cn_path}")
    
    return True


def run_check(force: bool = False, headless: bool = True, use_api: bool = False, api_key: str | None = None):
    """执行一次检查
    
    Args:
        force: 是否强制重新处理
        headless: 是否使用 headless 模式
        use_api: 是否使用API翻译
        api_key: API密钥
    """
    logger.info("=" * 60)
    logger.info("ITTF排名规则检查")
    logger.info("=" * 60)
    
    state = load_state()
    
    # 查找本地PDF
    local_pdfs = find_local_pdfs()
    if local_pdfs:
        logger.info(f"本地已有 {len(local_pdfs)} 个PDF文件:")
        for name in sorted(local_pdfs.keys()):
            logger.info(f"  - {name}")
    
    # 调用 scrape_regulations 获取最新规则
    logger.info("正在从 ITTF 官网获取最新规则...")
    result = fetch_regulations(
        download_dir=DOCS_DIR,
        output_path=DATA_DIR / "regulations" / "latest_regulations.json",
        skip_download=False,
        skip_extract=True,  # 我们自己在 process_pdf 中提取
        headless=headless,
        slow_mo=100,
    )
    
    if not result["success"]:
        logger.error(f"获取规则失败: {result.get('error', '未知错误')}")
        if local_pdfs:
            latest = sorted(local_pdfs.keys())[-1]
            logger.info(f"使用本地最新版本: {latest}")
            process_pdf(local_pdfs[latest], force=force, use_api=use_api, api_key=api_key)
        return
    
    downloaded_file = result["downloaded_file"]
    if downloaded_file and downloaded_file.exists():
        process_pdf(downloaded_file, force=force, use_api=use_api, api_key=api_key)
    else:
        logger.error("下载文件不存在")


def run_daemon(headless: bool = True, use_api: bool = False, api_key: str | None = None):
    """持续运行，每3天检查一次
    
    Args:
        headless: 是否使用 headless 模式
        use_api: 是否使用API翻译
        api_key: API密钥
    """
    logger.info("=" * 60)
    logger.info("ITTF排名规则监控服务已启动")
    logger.info(f"检查间隔: 每3天")
    logger.info("按 Ctrl+C 停止")
    logger.info("=" * 60)
    
    while True:
        try:
            run_check(headless=headless, use_api=use_api, api_key=api_key)
            logger.info(f"下次检查: {datetime.now() + timedelta(seconds=CHECK_INTERVAL)}")
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            logger.info("服务已停止")
            break
        except Exception as e:
            logger.error(f"运行时错误: {e}")
            # 等待1小时后重试
            time.sleep(3600)


def main():
    parser = argparse.ArgumentParser(
        description='ITTF排名规则文件管理器 - 获取、处理、翻译规则文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    %(prog)s                           # 运行一次检查
    %(prog)s --force                   # 强制重新处理所有文件
    %(prog)s --daemon                  # 持续运行模式，每3天检查一次
    %(prog)s --translate               # 仅翻译已有PDF
    %(prog)s --headless                # 使用 headless 模式抓取
    %(prog)s --api --api-key YOUR_KEY  # 使用 MiniMax API 翻译
        """
    )
    parser.add_argument('--daemon', '-d', action='store_true',
                        help='持续运行模式，每3天检查一次')
    parser.add_argument('--force', '-f', action='store_true',
                        help='强制重新处理所有文件')
    parser.add_argument('--translate', '-t', action='store_true',
                        help='仅翻译已有PDF')
    parser.add_argument('--pdf', '-p', type=str,
                        help='指定要处理的PDF文件路径')
    parser.add_argument('--headless', action='store_true', default=True,
                        help='使用 headless 模式抓取（默认启用）')
    parser.add_argument('--no-headless', action='store_true',
                        help='禁用 headless 模式，显示浏览器窗口')
    parser.add_argument('--api', action='store_true',
                        help='使用 MiniMax API 进行翻译')
    parser.add_argument('--api-key', type=str, default=os.environ.get('MINIMAX_API_KEY'),
                        help='MiniMax API 密钥（也可通过 MINIMAX_API_KEY 环境变量设置）')
    
    args = parser.parse_args()
    
    # 确保目录存在
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "regulations").mkdir(parents=True, exist_ok=True)
    
    headless = not args.no_headless if args.no_headless else args.headless
    use_api = args.api and args.api_key is not None
    
    if args.daemon:
        run_daemon(headless=headless, use_api=use_api, api_key=args.api_key)
    elif args.pdf:
        process_pdf(Path(args.pdf), force=args.force, use_api=use_api, api_key=args.api_key)
    elif args.translate:
        local_pdfs = find_local_pdfs()
        for name, path in sorted(local_pdfs.items()):
            process_pdf(path, force=True, use_api=use_api, api_key=args.api_key)
    else:
        run_check(force=args.force, headless=headless, use_api=use_api, api_key=args.api_key)


if __name__ == "__main__":
    main()
