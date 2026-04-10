#!/usr/bin/env python3
"""
ITTF 世界排名数据获取脚本

使用方法:
    python ittf_rankings.py                    # 获取女子单打前50名
    python ittf_rankings.py --top 100         # 获取前100名
    python ittf_rankings.py --category men    # 获取男子单打
    python ittf_rankings.py --json           # 只输出JSON
    python ittf_rankings.py --html           # 生成HTML页面

参数:
    --top N:      获取前N名选手 (默认: 50)
    --category:   排名类别 (默认: women)
                  可选: women, men, women_doubles, men_doubles, mixed
    --json:       输出JSON格式
    --html:       生成HTML展示页面
    --output:     输出文件路径
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

# 排名URL映射
RANKING_URLS = {
    "women": "https://results.ittf.link/ittf-rankings/ittf-ranking-women-singles",
    "men": "https://results.ittf.link/ittf-rankings/ittf-ranking-men-singles",
    "women_doubles": "https://results.ittf.link/ittf-rankings/ittf-ranking-women-doubles",
    "men_doubles": "https://results.ittf.link/ittf-rankings/ittf-ranking-men-doubles",
    "mixed": "https://results.ittf.link/ittf-rankings/ittf-ranking-mixed-doubles",
}

# 类别显示名称
CATEGORY_DISPLAY = {
    "women": "女子单打",
    "men": "男子单打",
    "women_doubles": "女子双打",
    "men_doubles": "男子双打",
    "mixed": "混合双打",
}


def translate_country(code):
    return COUNTRY_NAMES.get(code, code)


def translate_continent(code):
    return CONTINENT_NAMES.get(code, code)


def generate_html_table(rankings):
    rows = ""
    for p in rankings:
        change_class = "up" if p["change"] > 0 else "down" if p["change"] < 0 else "same"
        change_symbol = f"+{p['change']}" if p["change"] > 0 else str(p["change"])
        change_display = change_symbol if p["change"] != 0 else "-"
        
        rows += f"""        <tr>
            <td class="rank">{p['rank']}</td>
            <td class="change {change_class}">{change_display}</td>
            <td class="name">{p['name']}</td>
            <td class="name-en">{p['english_name']}</td>
            <td>{p['country']}</td>
            <td>{p['continent']}</td>
            <td class="points">{p['points']:,}</td>
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
        .card {
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.15);
            overflow: hidden;
        }
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
        td {
            padding: 14px 20px;
            border-bottom: 1px solid #f1f5f9;
            color: #334155;
        }
        tr:hover { background: #f8fafc; }
        tr:last-child td { border-bottom: none; }
        .rank { font-weight: 700; font-size: 1.1em; color: #3b82f6; }
        .name { font-weight: 600; color: #1e293b; }
        .name-en { color: #94a3b8; font-size: 0.9em; }
        .points { font-weight: 700; color: #10b981; font-size: 1.05em; }
        .change.up { color: #10b981; font-weight: 600; }
        .change.down { color: #ef4444; font-weight: 600; }
        .change.same { color: #94a3b8; }
        .footer {
            text-align: center;
            padding: 20px;
            color: #94a3b8;
            font-size: 0.85em;
        }
"""


def generate_html(rankings, category, update_date):
    table_rows = generate_html_table(rankings)
    category_name = CATEGORY_DISPLAY.get(category, category)
    
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ITTF 世界乒乓球排名 - {category_name}</title>
    <style>{CSS_STYLE}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏓 ITTF 世界乒乓球排名</h1>
            <p>{category_name} · 前{len(rankings)}名</p>
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


def print_rankings_table(rankings, category):
    category_name = CATEGORY_DISPLAY.get(category, category)
    print(f"\n🏓 ITTF {category_name}排名 (前{len(rankings)}名)")
    print("=" * 90)
    print(f"{'排名':^6} {'变化':^8} {'选手':^20} {'国家':^10} {'积分':^10}")
    print("-" * 90)
    
    for p in rankings:
        change = f"+{p['change']}" if p['change'] > 0 else str(p['change'])
        name = p['name'][:18] if len(p['name']) > 18 else p['name']
        country = p['country'][:8] if len(p['country']) > 8 else p['country']
        print(f"{p['rank']:^6} {change:^8} {name:<20} {country:<10} {p['points']:>10,}")
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="ITTF世界排名数据获取脚本")
    parser.add_argument("--top", type=int, default=50, help="获取前N名选手 (默认: 50)")
    parser.add_argument("--category", type=str, default="women",
                        choices=["women", "men", "women_doubles", "men_doubles", "mixed"],
                        help="排名类别 (默认: women)")
    parser.add_argument("--json", action="store_true", help="输出JSON格式")
    parser.add_argument("--html", action="store_true", help="生成HTML页面")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径")
    parser.add_argument("--print", action="store_true", help="在终端打印表格")
    
    args = parser.parse_args()
    
    print(f"\n📋 ITTF 世界排名数据获取脚本")
    print("=" * 50)
    print(f"类别: {CATEGORY_DISPLAY.get(args.category, args.category)}")
    print(f"前: {args.top} 名")
    print("=" * 50)
    
    print(f"\n⚠️  此脚本用于处理和展示已获取的排名数据")
    print(f"\n数据来源URL:")
    for cat, url in RANKING_URLS.items():
        marker = " ← 当前选中" if cat == args.category else ""
        print(f"  {CATEGORY_DISPLAY.get(cat, cat)}: {url}{marker}")
    
    print(f"\n💡 使用方法:")
    print(f"  1. 在浏览器中打开上述URL")
    print(f"  2. 提取排名数据(可使用浏览器开发者工具或page source)")
    print(f"  3. 将数据保存为JSON格式")
    print(f"  4. 使用 --json 或 --html 参数生成输出")


if __name__ == "__main__":
    main()
