#!/usr/bin/env python3
"""
ITTF排名规则自动检查、下载、转换和翻译脚本

功能：
- 每3天检查 ITTF 官网是否有新的排名规则 PDF
- 下载最新的 PDF 文件
- 转换为 Markdown 格式
- 翻译成中文

使用方法：
    python ittf_rankings_updater.py              # 运行一次检查
    python ittf_rankings_updater.py --force      # 强制下载并处理
    python ittf_rankings_updater.py --daemon     # 持续运行，每3天检查一次
    python ittf_rankings_updater.py --translate  # 仅翻译已有PDF

依赖：
    pip install requests pypdf beautifulsoup4
"""

import os
import sys
import time
import hashlib
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

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
STATE_FILE = SCRIPT_DIR / ".ittf_updater_state.json"

# ITTF 官网URL
ITTF_RANKINGS_URL = "https://ittf.com/rankings"
ITTF_PDF_BASE_URL = "https://www.ittf.com/wp-content/uploads"

# 检查间隔（秒）- 3天
CHECK_INTERVAL = 3 * 24 * 60 * 60

# 已知的规则文件模式
KNOWN_PATTERNS = [
    "ITTF-Table-Tennis-World-Ranking-Regulations",
    "World-Ranking-Regulations",
    "ITTF-Ranking-Regulations",
]


def get_latest_pdf_info():
    """从ITTF官网检查最新的规则PDF信息"""
    import requests
    from bs4 import BeautifulSoup
    
    logger.info(f"正在检查 ITTF 官网: {ITTF_RANKINGS_URL}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(ITTF_RANKINGS_URL, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 查找PDF下载链接
        pdf_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '.pdf' in href.lower() and any(p in href for p in KNOWN_PATTERNS):
                pdf_links.append(href)
        
        # 也检查页面文本中的PDF引用
        page_text = soup.get_text()
        for pattern in KNOWN_PATTERNS:
            if pattern in page_text:
                logger.info(f"在页面中发现规则引用: {pattern}")
        
        # 返回找到的PDF链接
        if pdf_links:
            logger.info(f"找到 {len(pdf_links)} 个相关PDF链接")
            return pdf_links
        
        return []
        
    except Exception as e:
        logger.error(f"检查官网失败: {e}")
        return []


def download_pdf(url, dest_path):
    """下载PDF文件"""
    import requests
    
    logger.info(f"正在下载: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(dest_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"已保存到: {dest_path}")
        return True
        
    except Exception as e:
        logger.error(f"下载失败: {e}")
        return False


def extract_pdf_to_markdown(pdf_path, md_path):
    """从PDF提取文本并保存为Markdown"""
    import pypdf
    
    logger.info(f"正在提取PDF内容: {pdf_path}")
    
    try:
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
        return True
        
    except Exception as e:
        logger.error(f"PDF提取失败: {e}")
        return False


def translate_to_chinese(md_path, cn_path, use_api=False, api_key=None):
    """将英文Markdown翻译成中文
    
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
            # 使用MiniMax API进行翻译
            logger.info("使用MiniMax API翻译...")
            translated = translate_with_minimax(content, api_key)
            if translated:
                with open(cn_path, 'w', encoding='utf-8', newline='') as f:
                    f.write(translated)
                logger.info(f"中文文档已保存: {cn_path}")
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


def translate_with_minimax(content, api_key):
    """使用MiniMax API进行翻译"""
    import json
    
    prompt = f"""请将以下ITTF世界乒乓球排名规则的英文文档翻译成中文。

要求：
1. 保持原有格式和结构（标题、表格、列表等）
2. 准确翻译专业术语（积分、轮次、资格赛等）
3. 表格保持原样格式
4. 添加页脚说明（文件来源、最后更新日期、原文链接）

以下是文档内容：

{content[:8000]}"""
    
    try:
        import urllib.request
        
        url = "https://api.minimax.chat/v1/text/chatcompletion_pro?GroupId=your_group_id"
        
        # 如果没有配置GroupId，使用简单方式
        data = json.dumps({
            "model": "MiniMax-Text-01",
            "messages": [
                {"role": "system", "content": "你是一个专业的体育规则文档翻译助手。"},
                {"role": "user", "content": prompt}
            ]
        }).encode('utf-8')
        
        req = urllib.request.Request(
            'https://api.minimax.chat/v1/text/chatcompletion_pro',
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            if 'choices' in result:
                return result['choices'][0]['message']['content']
        
        return None
        
    except Exception as e:
        logger.error(f"MiniMax API调用失败: {e}")
        return None


def get_file_hash(file_path):
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
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    
    return {
        'last_check': None,
        'last_pdf_hash': None,
        'last_pdf_name': None,
        'versions_processed': []
    }


def save_state(state):
    """保存运行状态"""
    import json
    
    with open(STATE_FILE, 'w', newline='') as f:
        json.dump(state, f, indent=2)


def find_local_pdfs():
    """查找本地已有的PDF文件"""
    pdfs = {}
    if DOCS_DIR.exists():
        for f in DOCS_DIR.glob("*.pdf"):
            pdfs[f.name] = f
    return pdfs


def process_pdf(pdf_path, force=False):
    """处理单个PDF文件"""
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
    for pattern in [r'(\d{8})', r'(\d{4}-\d{2}-\d{2})', r'(\d{4})(\d{2})(\d{2})']:
        import re
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
    
    # 提取PDF内容
    if not extract_pdf_to_markdown(pdf_path, md_path):
        return False
    
    # 翻译
    translate_to_chinese(md_path, cn_path)
    
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


def run_check():
    """执行一次检查"""
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
    
    # 检查官网
    pdf_links = get_latest_pdf_info()
    
    if not pdf_links:
        logger.info("未发现新的PDF文件")
        if local_pdfs:
            latest = sorted(local_pdfs.keys())[-1]
            logger.info(f"使用本地最新版本: {latest}")
            process_pdf(local_pdfs[latest])
        return
    
    # 下载最新的PDF
    for url in pdf_links:
        filename = url.split('/')[-1]
        dest_path = DOCS_DIR / filename
        
        if dest_path.exists():
            logger.info(f"文件已存在: {filename}")
            process_pdf(dest_path)
        else:
            if download_pdf(url, dest_path):
                process_pdf(dest_path)


def run_daemon():
    """持续运行，每3天检查一次"""
    logger.info("=" * 60)
    logger.info("ITTF排名规则监控服务已启动")
    logger.info(f"检查间隔: 每3天")
    logger.info("按 Ctrl+C 停止")
    logger.info("=" * 60)
    
    while True:
        try:
            run_check()
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
    parser = argparse.ArgumentParser(description='ITTF排名规则自动更新工具')
    parser.add_argument('--daemon', '-d', action='store_true',
                        help='持续运行模式，每3天检查一次')
    parser.add_argument('--force', '-f', action='store_true',
                        help='强制重新处理所有文件')
    parser.add_argument('--translate', '-t', action='store_true',
                        help='仅翻译已有PDF')
    parser.add_argument('--pdf', '-p', type=str,
                        help='指定要处理的PDF文件路径')
    
    args = parser.parse_args()
    
    # 确保目录存在
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.daemon:
        run_daemon()
    elif args.pdf:
        process_pdf(Path(args.pdf), force=args.force)
    elif args.translate:
        local_pdfs = find_local_pdfs()
        for name, path in local_pdfs.items():
            process_pdf(path, force=True)
    else:
        run_check()


if __name__ == "__main__":
    main()
