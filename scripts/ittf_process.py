#!/usr/bin/env python3
"""
ITTF 世界排名数据处理脚本

功能:
1. 读取JSON格式的排名数据
2. 生成美观的HTML展示页面
3. 支持命令行参数配置

使用方法:
    # 基本用法 - 读取data目录下的默认数据文件
    python ittf_process.py
    
    # 指定输入文件
    python ittf_process.py --input data.json
    
    # 指定输出文件
    python ittf_process.py --output my_rankings.html
    
    # 只处理前20名
    python ittf_process.py --top 20
    
    # 打印到终端
    python ittf_process.py --print
    
    # 生成完整报告
    python ittf_process.py --json --html --print
"""

import argparse
import json
from datetime import datetime
from pathlib import Path


# 国家/地区代码到中文名称的映射
COUNTRY_NAMES = {
    "CHN": "中国", "JPN": "日本", "KOR": "韩国", "GER": "德国",
    "FRA": "法国", "USA": "美国", "HKG": "中国香港", "TPE": "中国台北",
    "MAC": "中国澳门", "SGP": "新加坡", "BRA": "巴西", "EGY": "埃及",
    "IND": "印度", "ROU": "罗马尼亚", "AUT": "奥地利", "NED": "荷兰",
    "SWE": "瑞典", "POL": "波兰", "ESP": "西班牙", "ITA": "意大利",
    "ENG": "英格兰", "WAL": "威尔士", "SCO": "苏格兰", "AUS": "澳大利亚",
    "NZL": "新西兰", "CAN": "加拿大", "MEX": "墨西哥", "ARG": "阿根廷",
    "PUR": "波多黎各", "DOM": "多米尼加", "CZE": "捷克", "RUS": "俄罗斯",
    "UKR": "乌克兰", "TUR": "土耳其", "IRI": "伊朗", "THA": "泰国",
    "VIE": "越南", "INA": "印度尼西亚", "MAS": "马来西亚", "PHI": "菲律宾",
    "PAK": "巴基斯坦", "KAZ": "哈萨克斯坦", "UZB": "乌兹别克斯坦",
    "SIN": "新加坡", "AIN": "中立运动员",
}

# 大洲代码到中文的映射
CONTINENT_NAMES = {
    "ASIA": "亚洲", "EUROPE": "欧洲", "AMERICA": "美洲",
    "AFRICA": "非洲", "OCEANIA": "大洋洲",
}

# 类别显示名称
CATEGORY_DISPLAY = {
    "women_singles": "女子单打",
    "men_singles": "男子单打",
    "women_doubles": "女子双打",
    "men_doubles": "男子双打",
    "mixed_doubles": "混合双打",
    "women": "女子单打",
    "men": "男子单打",
}


def translate_country(code):
    """将国家代码翻译为中文"""
    return COUNTRY_NAMES.get(code, code)


def translate_continent(code):
    """将大洲代码翻译为中文"""
    return CONTINENT_NAMES.get(code, code)


def ensure_chinese_names(rankings):
    """确保数据中有中文名字"""
    for p in rankings:
        # 如果没有中文名，使用英文名
        if 'name' not in p or not p['name']:
            p['name'] = p.get('english_name', p.get('name_en', ''))
        # 如果没有英文名，使用中文名
        if 'english_name' not in p or not p['english_name']:
            p['english_name'] = p.get('name', '')
        # 确保国家名称是中文
        if 'country' not in p or not p['country']:
            country_code = p.get('country_code', '')
            p['country'] = translate_country(country_code)
        # 确保大洲名称是中文
        if 'continent' not in p or not p['continent']:
            p['continent'] = translate_continent(p.get('continent_code', 'ASIA'))
    return rankings


def generate_table_rows(rankings):
    """生成HTML表格行"""
    rows = ""
    for p in rankings:
        # 排名变化样式
        change = p.get('change', 0)
        if change > 0:
            change_class = "up"
            change_symbol = f"+{change}"
        elif change < 0:
            change_class = "down"
            change_symbol = str(change)
        else:
            change_class = "same"
            change_symbol = "-"
        
        # 积分格式化
        points = p.get('points', 0)
        
        rows += f"""        <tr>
            <td class="rank">{p['rank']}</td>
            <td class="change {change_class}">{change_symbol}</td>
            <td class="name">{p['name']}</td>
            <td class="name-en">{p['english_name']}</td>
            <td>{p['country']}</td>
            <td>{p['continent']}</td>
            <td class="points">{points:,}</td>
        </tr>
"""
    return rows


CSS_STYLE = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { 
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    padding: 30px 20px;
}
.container { max-width: 1100px; margin: 0 auto; }
.header { text-align: center; color: white; margin-bottom: 30px; }
.header h1 { font-size: 2.5em; margin-bottom: 10px; }
.header p { opacity: 0.9; font-size: 1.1em; }
.card { background: white; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.15); overflow: hidden; }
.card-header {
    background: linear-gradient(90deg, #3b82f6, #8b5cf6);
    color: white;
    padding: 20px 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.card-header h2 { font-size: 1.5em; }
.card-header .date { opacity: 0.9; font-size: 0.9em; }
table { width: 100%; border-collapse: collapse; }
th {
    background: #f8fafc;
    color: #64748b;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.75em;
    letter-spacing: 0.05em;
    padding: 16px 20px;
    text-align: left;
    border-bottom: 2px solid #e2e8f0;
}
td { padding: 14px 20px; border-bottom: 1px solid #f1f5f9; color: #334155; }
tr:hover { background: #f8fafc; }
tr:last-child td { border-bottom: none; }
.rank { font-weight: 700; font-size: 1.1em; color: #3b82f6; }
.name { font-weight: 600; color: #1e293b; }
.name-en { color: #94a3b8; font-size: 0.9em; }
.points { font-weight: 700; color: #10b981; font-size: 1.05em; }
.change.up { color: #10b981; font-weight: 600; }
.change.down { color: #ef4444; font-weight: 600; }
.change.same { color: #94a3b8; }
.footer { text-align: center; padding: 20px; color: #94a3b8; font-size: 0.85em; }
"""


def generate_html(rankings, category, update_date, title=None):
    """生成完整的HTML页面"""
    table_rows = generate_table_rows(rankings)
    category_name = CATEGORY_DISPLAY.get(category, category)
    if title is None:
        title = f"ITTF 世界乒乓球排名 - {category_name}"
    
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{CSS_STYLE}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏓 ITTF 世界乒乓球排名</h1>
            <p>{category_name} · TOP {len(rankings)}</p>
        </div>
        <div class="card">
            <div class="card-header">
                <h2>{category_name}</h2>
                <span class="date">更新: {update_date}</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>变化</th>
                        <th>选手</th>
                        <th>英文名</th>
                        <th>国家/地区</th>
                        <th>大洲</th>
                        <th>积分</th>
                    </tr>
                </thead>
                <tbody>
{table_rows}
                </tbody>
            </table>
        </div>
        <div class="footer">
            数据来源: ITTF · 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>"""


def print_table(rankings, category):
    """在终端打印表格"""
    category_name = CATEGORY_DISPLAY.get(category, category)
    print(f"\n🏓 ITTF {category_name}排名 (TOP {len(rankings)})")
    print("=" * 100)
    print(f"{'排名':^6} {'变化':^8} {'选手':<20} {'国家':<12} {'积分':>12}")
    print("-" * 100)
    
    for p in rankings:
        change = p.get('change', 0)
        change_str = f"+{change}" if change > 0 else str(change) if change < 0 else "-"
        name = p['name'][:18]
        country = p['country'][:10]
        points = p.get('points', 0)
        
        print(f"{p['rank']:^6} {change_str:^8} {name:<20} {country:<12} {points:>12,}")
    
    print("=" * 100)


def save_json(rankings, category, update_date, output_file):
    """保存为JSON格式"""
    data = {
        "update_date": update_date,
        "category": category,
        "total_players": len(rankings),
        "rankings": rankings
    }
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return output_file


def main():
    parser = argparse.ArgumentParser(description="ITTF世界排名数据处理脚本")
    parser.add_argument("--input", "-i", type=str, default=None,
                        help="输入JSON文件路径")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="输出HTML文件路径")
    parser.add_argument("--top", "-n", type=int, default=50,
                        help="处理前N名选手 (默认: 50)")
    parser.add_argument("--category", "-c", type=str, default="women_singles",
                        help="排名类别 (默认: women_singles)")
    parser.add_argument("--json", action="store_true",
                        help="输出JSON格式")
    parser.add_argument("--html", action="store_true",
                        help="生成HTML页面")
    parser.add_argument("--print", action="store_true",
                        help="在终端打印表格")
    
    args = parser.parse_args()
    
    # 默认输入文件
    if args.input is None:
        # 尝试查找默认数据文件
        default_files = [
            Path("data/women_singles_top100.json"),
            Path("data/women_singles_top50.json"),
            Path("../data/women_singles_top100.json"),
            Path("../data/women_singles_top50.json"),
        ]
        for f in default_files:
            if f.exists():
                args.input = str(f)
                break
    
    # 读取数据
    if args.input is None or not Path(args.input).exists():
        print("❌ 错误: 未找到输入文件")
        print("\n使用方法:")
        print("  python ittf_process.py --input data.json")
        print("  python ittf_process.py -i data.json -o output.html")
        return
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 获取排名数据
    rankings = data.get('rankings', data if isinstance(data, list) else [])
    rankings = rankings[:args.top]  # 只处理前N名
    
    # 确保中文名称
    rankings = ensure_chinese_names(rankings)
    
    # 更新日期
    update_date = data.get('update_date', datetime.now().strftime("%Y年%m月%d日"))
    
    # 类别
    category = data.get('category', args.category)
    
    print("=" * 60)
    print("📋 ITTF 世界排名数据处理")
    print("=" * 60)
    print(f"✅ 数据读取成功: {args.input}")
    print(f"📊 选手数量: {len(rankings)}")
    print(f"📅 更新日期: {update_date}")
    print(f"🏷️  类别: {CATEGORY_DISPLAY.get(category, category)}")
    print()
    
    # 打印前10名
    print("TOP 10 预览:")
    for i, p in enumerate(rankings[:10], 1):
        change = p.get('change', 0)
        change_str = f"+{change}" if change > 0 else str(change) if change < 0 else "-"
        print(f"  {i:2}. {p['name']} ({p['country']}) - {p.get('points', 0):,}分 [{change_str}]")
    print()
    
    # 生成输出
    if args.html or args.output:
        output_file = args.output or args.input.replace('.json', '.html')
        html = generate_html(rankings, category, update_date)
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            f.write(html)
        print(f"✅ HTML页面已生成: {output_file}")
    
    if args.json:
        output_file = args.input.replace('.json', '_processed.json')
        save_json(rankings, category, update_date, output_file)
        print(f"✅ JSON数据已保存: {output_file}")
    
    if args.print:
        print_table(rankings, category)
    
    print("\n🎉 处理完成！")


if __name__ == "__main__":
    main()
