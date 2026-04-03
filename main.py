# astrbot_plugin_galnews/main.py
import os, json, asyncio, aiohttp, urllib.parse
from pathlib import Path
from typing import Dict, List
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger # 按照审核建议改用框架 logger

@register("astrbot_plugin_galnews", "Care", "Galgame 资讯与订阅", "1.1.4")
class GalNewsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.io_lock = asyncio.Lock()
        # 修复路径获取，防止 join 错误
        from astrbot.api.star import StarTools
        try:
            self.base_path = str(StarTools.get_data_dir())
        except:
            self.base_path = os.path.join(os.getcwd(), "data", "plugins", "galnews")
        os.makedirs(self.base_path, exist_ok=True)
        
        self.bgm_token = "McT3CzkJaKQs45WYRfhUU0oB8ejvE1Aj5WGYLm2J"
        self.vndb_token = "zkxy-bidaq-8coke-gzoy-gdem1-9zscs-kcdf"
        self.ua = "Care/astrbot_plugin_galnews (https://github.com/Care0721)"

    async def fetch_api(self, url, headers, method="GET", json_data=None):
        """通用网络请求工具，增加超时控制"""
        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers, timeout=8) as r:
                        return await r.json() if r.status == 200 else None
                else:
                    async with session.post(url, headers=headers, json=json_data, timeout=8) as r:
                        return await r.json() if r.status == 200 else None
        except: return None

    @filter.command("monigalnews") # 匹配你截图中的命令名
    async def get_gal_news(self, event: AstrMessageEvent, game: str = ""):
        if not game.strip(): return
        
        yield event.plain_result(f"📡 正在获取《{game}》的视觉情报...")
        
        # 1. 获取 Bangumi 数据
        q = urllib.parse.quote(game)
        bgm_data = await self.fetch_api(f"https://api.bgm.tv/search/subject/{q}?type=4", {"Authorization": f"Bearer {self.bgm_token}", "User-Agent": self.ua})
        
        # 2. 获取 VNDB 数据
        vndb_payload = {"filters": ["search", "=", game], "fields": "title, released, rating, image.url"}
        vndb_data = await self.fetch_api("https://beta.vndb.org/api/kana/vn", {"Content-Type": "application/json", "Authorization": f"token {self.vndb_token}", "User-Agent": self.ua}, "POST", vndb_payload)

        # 提取数据与图片
        img = None
        report = f"🎯【《{game}》检索报告】🎯\n\n"
        
        if bgm_data and bgm_data.get('list'):
            item = bgm_data['list'][0]
            img = item.get('images', {}).get('large')
            report += f"🔵 --- Bangumi ---\n译名: {item.get('name_cn') or '无'}\n评分: {item.get('rating', {}).get('score') or '暂无'}\n"
        
        if vndb_data and vndb_data.get('results'):
            item = vndb_data['results'][0]
            if not img: img = item.get('image', {}).get('url')
            report += f"🔴 --- VNDB ---\n标题: {item.get('title')}\n评分: {round(float(item.get('rating', 0))/10, 1) if item.get('rating') else '暂无'}"

        # 稳健发送：先发图（如果有），再发文字
        if img:
            try: yield event.image_result(img)
            except: pass 
        yield event.plain_result(report)
