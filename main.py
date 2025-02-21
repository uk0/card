import json

import requests
from fastapi import FastAPI, Response, Query
from typing import Optional
import time

from linux_do import SvgCardService

app = FastAPI()
# 创建一个 SvgCardService 实例
card_service = SvgCardService(
    base_url="https://linux.do",       # 远端基础URL，可根据需求调整
    cache_expire_seconds=600
)

@app.get("/card/{username}.svg", response_class=Response)
def get_card(username: str,theme: Optional[str] = Query("auto")) -> Response:
    """
    访问 /card/{username} 即可生成并返回该用户的SVG名片。
    """
    try:
        svg_content = card_service.get_user_svg_card(username,theme)
        return Response(content=svg_content, media_type="image/svg+xml")
    except requests.HTTPError as e:
        # 如果请求出错，比如用户不存在，或远程无法访问
        error_svg = f'''<svg width="400" height="100" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" fill="#fff"/>
        <text x="20" y="50" font-size="16" fill="red">
          Error fetching data for user: {username}. Detail: {str(e)}
        </text></svg>'''
        return Response(content=error_svg, media_type="image/svg+xml", status_code=404)
    except Exception as ex:
        # 其它意外错误
        error_svg = f'''<svg width="400" height="100" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" fill="#fff"/>
        <text x="20" y="50" font-size="16" fill="red">
          Unknown error: {str(ex)}
        </text></svg>'''
        return Response(content=error_svg, media_type="image/svg+xml", status_code=500)