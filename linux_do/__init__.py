import datetime
import json
import os
import time
import requests
from typing import Dict, Any, Optional


import markdown
from bs4 import BeautifulSoup

def markdown_to_plaintext(md_text: str) -> str:
    """将 Markdown 转为纯文本"""
    # 1) 先转为 HTML
    html = markdown.markdown(md_text)

    # 2) 用 BeautifulSoup 去掉所有 HTML 标签，提取文本
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")  # 用换行符分隔
    return text

class SvgCardService:
    """
    封装一个通用的接口类，用来获取某个用户的数据并生成SVG名片。
    """
    def __init__(
        self,
        base_url: str = "https://linux.do",   # 示例远端地址
        cache_expire_seconds: int = 222       # 缓存过期时间(秒)
    ):
        """
        :param base_url: 用于获取用户数据的基本地址，如 "https://linux.do"
        :param cache_expire_seconds: 缓存过期时间，默认600秒(10分钟)
        """
        self.base_url = base_url
        self.cache_expire_seconds = cache_expire_seconds
        # 简易内存缓存结构: { username: { "data": {...}, "cached_at": <timestamp> } }
        self.cache: Dict[str, Dict[str, Any]] = {}

    def get_user_data(self, username: str) -> dict:
        """
        获取用户信息，先查缓存，如果过期或没有，则请求远端接口。
        在这里可以根据实际需要修改获取数据的方式(读文件/调API/数据库等)
        """
        current_time = time.time()
        # 1) 检查缓存
        if username in self.cache:
            cached_item = self.cache[username]
            if (current_time - cached_item["cached_at"]) < self.cache_expire_seconds:
                print("[DEBUG] Using cached data for", username)
                return cached_item["data"]  # 缓存未过期，直接返回

        # 2) 如果缓存无效，重新请求
        summary_url = f"{self.base_url}/u/{username}/summary.json"
        detail_url  = f"{self.base_url}/u/{username}.json"
        try:
            summary_resp = requests.get(summary_url, timeout=10)
            detail_resp  = requests.get(detail_url, timeout=10)

            summary_resp.raise_for_status()
            detail_resp.raise_for_status()

            summary_data = summary_resp.json()  # summary.json
            detail_data  = detail_resp.json()   # .json

            # 合并一下，或根据需要的字段结构自定义
            data = {
                "summary": summary_data,
                "detail" : detail_data
            }
            if os.environ.get("SAVE_JSON"):
                self.save_dict_as_json(data, f"{username}.json")
        except requests.RequestException as e:
            # 如果请求异常，抛出，让外层捕捉处理
            raise RuntimeError(f"Failed to fetch data for {username}: {e}")

        # 3) 写入缓存
        self.cache[username] = {
            "data": data,
            "cached_at": current_time
        }
        print("[DEBUG] Fetched data for", username)
        return data

    import datetime

    def _format_created_date(self,date_str: str) -> str:
        """
        解析形如 "2025-01-13T17:12:12.556Z" 的 UTC 时间，
        返回 "YYYY-MM-DD" 格式字符串。
        如果解析失败，则返回 "N/A"。
        """
        if not date_str or date_str == "N/A":
            return "N/A"
        try:
            # "%Y-%m-%dT%H:%M:%S.%fZ" 能解析类似 "2025-01-13T17:12:12.556Z"
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            # 如果小数秒不是6位等原因，可尝试更通用的格式，或作兼容处理
            try:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return "N/A"

    def _format_last_seen(self,date_str: str) -> str:
        """
        解析形如 "2025-01-13T17:12:12.556Z" 的 UTC 时间，
        与当前时间做差，返回:
          - "刚刚" (小于1分钟)
          - "X 分钟前" (小于24小时)
          - "X 天前"   (大于等于24小时)
        解析失败返回 "N/A"。
        """
        if not date_str or date_str == "N/A":
            return "N/A"
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            # 如果毫秒部分不一样，可再试
            try:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                return "N/A"

        now_utc = datetime.datetime.utcnow()
        delta = now_utc - dt
        secs = delta.total_seconds()

        if secs < 60:
            # 小于1分钟 => 刚刚
            return "刚刚"

        # 转换为分钟
        minutes = int(secs // 60)
        if minutes < 24 * 60:
            # 小于24小时 => X分钟前
            return f"{minutes} 分钟前"

        # 大于等于24小时 => X天前
        days = int(minutes // (24 * 60))
        return f"{days} 天前"

    def generate_svg_card(
                self,
                data: dict,
                font_family: str = "sans-serif",
                theme: str = "dark",  # 增加 theme 参数/dark
                base_font_size: int = 16
        ) -> str:
            """
            将 SVG 分为 header / body / bottom 三大块，用横线分割：
              1) Header (0% ~ 20%)
                 显示: [用户名(等级)] / [用户签名] / [注册时间] / [最近上线]
              2) Body (20% ~ 85%)
                 显示: 键值对 (多行、每行最多3列)
              3) Bottom (85% ~ 100%)
                 一行文字，居中 "Generated by Qwq.chat"

            不使用 viewBox，而是 width="100%" height="100%"，并且用百分比 + vmin 字体大小。
            新增 theme 参数控制背景色和字体颜色。
            """

            ###################
            # 0) 主题配色设置
            ###################
            themes = {
                "light": {
                    "bg_color": "#f9f9f9",
                    "text_color": "#333",
                    "secondary_color": "#555",
                    "signature_color": "#666",
                    "border_color": "#ccc",
                    "bottom_color": "#777"
                },
                "dark": {
                    "bg_color": "#2b2b2b",
                    "text_color": "#e0e0e0",
                    "secondary_color": "#aaaaaa",
                    "signature_color": "#cccccc",
                    "border_color": "#555555",
                    "bottom_color": "#999999"
                }
                # 可自行扩展更多主题
            }

            # 若传入的 theme 不存在，则回退到 light
            theme_config = themes.get(theme.lower(), themes["light"])
            bg_color = theme_config["bg_color"]
            text_color = theme_config["text_color"]
            secondary_color = theme_config["secondary_color"]
            signature_color = theme_config["signature_color"]
            border_color = theme_config["border_color"]
            bottom_color = theme_config["bottom_color"]

            ###################
            # 1) 解析用户信息
            ###################
            user_info = data.get("detail", {}).get("user", {})
            user_summary = data.get("summary", {}).get("user_summary", {})
            bio_raw = user_info.get("bio_raw", "这个人很懒，什么也没留下。")
            bio_text = markdown_to_plaintext(bio_raw)

            username = user_info.get("username", "Anonymous")
            trust_level = user_info.get("trust_level", 0)
            signature = f"{bio_text[:24]}..."

            created_at = user_info.get("created_at", "N/A")
            created_at_str = self._format_created_date(created_at)

            last_seen_at = user_info.get("last_seen_at", "N/A")
            last_seen_at_str = self._format_last_seen(last_seen_at)

            # 等级映射
            trust_map = {
                0: "🔰 萌新",
                1: "💡 初级佬友",
                2: "🚀 二级佬友",
                3: "🌕 三级佬有",
                4: "🛠️ 管理员/版主"
            }
            rank_name = trust_map.get(trust_level, f"Lv{trust_level}")

            user_header_str = f"👋 {username}（{rank_name}）"

            ###################
            # 2) Body 键值对
            ###################
            # 转为小时
            time_read_seconds = user_summary.get("time_read", 0)
            hours = round(time_read_seconds / 3600, 1)

            body_kv = [
                ("📆️ 访问天数", user_summary.get("days_visited", 0)),
                ("📝 主题数量", user_summary.get("topic_count", 0)),
                ("💬 帖子数量", user_summary.get("post_count", 0)),
                ("❤️ 收获点赞", user_summary.get("likes_received", 0)),
                ("👍 送出点赞", user_summary.get("likes_given", 0)),
                ("📖 阅读贴数", user_summary.get("posts_read_count", 0)),
                ("⏱️ 阅读时长", f"{hours} 小时"),
                ("👀 我的关注", user_info.get("total_following", 0)),
                ("💎 积分数量", user_info.get("gamification_score", 0)),
                ("🙋 粉丝数量", user_info.get("total_followers", 0)),
                ("🏠 主页访问", user_info.get("profile_view_count", 0)),
                ("🔎 浏览话题", user_summary.get("topics_entered", 0))
            ]

            ###################
            # 3) 样式 & 布局参数
            ###################
            base_vmin = max(base_font_size / 16, 1.0)

            header_top = 0
            header_bottom = 20
            body_top = 30
            body_bottom = 85
            footer_top = 85
            footer_bottom = 100

            body_line_height = 10
            col_widths = [5, 38, 65]

            ###################
            # 4) 生成主体 SVG
            ###################
            svg = f'''<svg
      width="100%"
      height="100%"
      xmlns="http://www.w3.org/2000/svg"
    >
      <style>
        .title {{
          font: {2.0 * base_vmin}vmin {font_family};
          fill: {text_color};
          font-weight: bold;
        }}
        .header_text {{
          font: {1.6 * base_vmin}vmin {font_family};
          fill: {secondary_color};
        }}
        .body_kv {{
          font: {1.4 * base_vmin}vmin {font_family};
          fill: {text_color};
        }}
        .signature {{
          font: {1.4 * base_vmin}vmin {font_family};
          fill: {signature_color};
          font-style: italic;
        }}
        .bottom_text {{
          font: {1.4 * base_vmin}vmin {font_family};
          fill: {bottom_color};
        }}
        .border_line {{
          stroke: {border_color};
          stroke-width: 0.2vmin;
          fill: none;
        }}
        .bg {{
          fill: {bg_color};
        }}
      </style>

      <!-- 背景 -->
      <rect class="bg" x="0" y="0" width="100%" height="100%" />

      <!-- Header部分 -->
      <text x="5%" y="{header_top + 8}%" class="title">{user_header_str}</text>

      <text x="5%" y="{header_top + 16}%" class="signature">{signature}</text>

      <text x="60%" y="{header_top + 8}%" class="header_text">🕒注册时间: {created_at_str}</text>
      <text x="60%" y="{header_top + 16}%" class="header_text">🕒近期上线: {last_seen_at_str}</text>

      <!-- 横线分割 (Header-Bottom) -->
      <line class="border_line" x1="0%" y1="{header_bottom}%" x2="100%" y2="{header_bottom}%" />

      <!-- Body部分 (30% ~ 85%) -->
    '''

            def chunked(iterable, chunk_size=3):
                for i in range(0, len(iterable), chunk_size):
                    yield iterable[i:i + chunk_size]

            current_y = body_top + 8
            lines = []
            for row_items in chunked(body_kv, 3):
                for col_idx, (k, v) in enumerate(row_items):
                    x_pos = col_widths[col_idx]
                    lines.append(
                        f'<text x="{x_pos}%" y="{current_y}%" class="body_kv">{k}: {v}</text>'
                    )
                current_y += body_line_height

            svg += "\n".join(lines)

            # 横线分割 (Body-Bottom)
            svg += f'''
      <line class="border_line" x1="0%" y1="{body_bottom}%" x2="100%" y2="{body_bottom}%" />
    '''

            # 底部
            svg += f'''
      <!-- Bottom部分 (85% ~ 100%) -->
      <text
        x="50%"
        y="{footer_top + 8}%"
        class="bottom_text"
        text-anchor="middle"
      >
        Generated by Qwq.chat
      </text>
    </svg>
    '''
            return svg

    def _auto_theme_by_time(self) -> str:
        """
        根据当前本地时间 (hour) 自动判断是 dark 还是 light:
          - 19:00 ~ 23:59 => dark
          - 00:00 ~ 06:00 => dark
          - 06:00 ~ 19:00 => light
        你可以按需修改时间范围。
        """
        now = datetime.datetime.now()
        hour = now.hour
        # 约定: 晚上7点(19)到凌晨6点(06) 都使用 dark
        if hour >= 19 or hour < 6:
            return "dark"
        else:
            return "light"

    def save_dict_as_json(self,data: dict, filename: str, ensure_ascii: bool = False, indent: int = 2):
        """
        将 Python dict 转换为 JSON 字符串并写入文件。

        :param data: 需要保存的 Python 字典
        :param filename: 保存的目标文件名（如 data.json）
        :param ensure_ascii: 是否将非 ASCII 字符转换为 \\uXXXX 形式，默认为 False
        :param indent: JSON 缩进层级，默认 2
        """
        with open(filename, 'w', encoding='utf-8') as f:
            # json.dump 将 Python 对象转换为 JSON 字符串并写入文件
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
    def get_user_svg_card(self, username: str,theme='') -> str:
        """
        上层统一方法：
        - 获取用户数据
        - 生成 SVG 内容
        - 返回 SVG 字符串
        """
        user_data = self.get_user_data(username)
        if theme=='auto':
            theme = self._auto_theme_by_time()
        elif theme in ['dark','light']:
            pass
        svg = self.generate_svg_card(data=user_data,theme=theme)
        return svg