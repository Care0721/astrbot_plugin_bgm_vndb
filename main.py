import os
import json
import asyncio
import aiohttp
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

try:
    from astrbot.api.star import StarTools
except ImportError:
    StarTools = None

@register("astrbot_plugin_galnews", "Care", "Galgame 资讯与订阅推送助手", "1.1.3")
class GalNewsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.io_lock = asyncio.Lock()
        self.base_path = self._get_safe_data_dir()
        self.subscriptions: Dict[str, List[str]] = {}
        
        # 🔑 API 配置
        self.bgm_token = "McT3CzkJaKQs45WYRfhUU0oB8ejvE1Aj5WGYLm2J"
        self.bgm_api = "https://api.bgm.tv"
        self.vndb_token = "zkxy-bidaq-8coke-gzoy-gdem1-9zscs-kcdf"
        self.vndb_api = "https://beta.vndb.org/api/kana/vn"
        self.user_agent = "Care/astrbot_plugin_galnews (https://github.com/Care0721)"
        
        self._load_data_sync()

    def _get_safe_data_dir(self) -> str:
        target_path = None
        if StarTools and hasattr(StarTools, "get_data_dir"):
            try:
                res = StarTools.get_data_dir()
                if isinstance(res, (str, Path)) and "GalNewsPlugin" not in str(res):
                    target_path = Path(res)
            except Exception:
                try:
                    res = StarTools.get_data_dir(self)
                    if isinstance(res, (str, Path)) and "GalNewsPlugin" not in str(res):
                        target_path = Path(res)
                except Exception: pass
        if not target_path:
            target_path = Path(__file__).parent.parent.parent / "data" / "plugins" / "astrbot_plugin_galnews"
        target_path.mkdir(parents=True, exist_ok=True)
        return str(target_path.absolute())

    def _load_data_sync(self):
        sub_file = os.path.join(self.base_path, "subscriptions.json")
        if not os.path.exists(sub_file):
            try:
                with open(sub_file, "w", encoding="utf-8") as f: json.dump({}, f)
            except Exception: pass
        try:
            with open(sub_file, "r", encoding="utf-8") as f: self.subscriptions = json.load(f)
        except Exception: self.subscriptions = {}

    # ================= 增强型 API 层（支持图片提取） =================

    async def fetch_bangumi(self, keyword: str):
        """返回 (文字信息, 图片URL)"""
        q = urllib.parse.quote(keyword)
        url = f"{self.bgm_api}/search/subject/{q}?type=4"
        headers = {"Authorization": f"Bearer {self.bgm_token}", "User-Agent": self.user_agent}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status != 200: return f"❌ BGM HTTP {resp.status}", None
                    data = await resp.json()
                    if not data.get("list"): return "🔍 查无此作", None
                    
                    item = data["list"][0]
                    name = item.get("name") or "未知"
                    name_cn = item.get("name_cn") or "暂无官方译名"
                    date = item.get("air_date") or "未知"
                    score = (item.get("rating") or {}).get("score") or "暂无评分"
                    
                    # 提取封面图
                    img_url = (item.get("images") or {}).get("large")
                    
                    info = f"原名: {name}\n译名: {name_cn}\n发售日: {date}\n评分: {score}"
                    return info, img_url
        except Exception as e:
            return f"⚠️ BGM异常: {e}", None

    async def fetch_vndb(self, keyword: str):
        """返回 (文字信息, 图片URL)"""
        # 增加 image 字段请求
        payload = {
            "filters": ["search", "=", keyword],
            "fields": "title, alttitle, released, rating, image.url"
        }
        headers = {"Content-Type": "application/json", "Authorization": f"token {self.vndb_token}", "User-Agent": self.user_agent}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.vndb_api, json=payload, headers=headers, timeout=12) as resp:
                    if resp.status != 200: return f"❌ VNDB HTTP {resp.status}", None
                    data = await resp.json()
                    if not data.get("results"): return "🔍 查无此作", None
                    
                    item = data["results"][0]
                    title = item.get("title") or "未知"
                    date = item.get("released") or "未知"
                    raw_rate = item.get("rating")
                    rating = round(float(raw_rate) / 10, 1) if raw_rate else "暂无评分"
                    
                    # 提取 VNDB 封面
                    img_url = (item.get("image") or {}).get("url")
                    
                    info = f"标题: {title}\n发售日: {date}\n评分: {rating}"
                    return info, img_url
        except Exception as e:
            return f"⚠️ VNDB异常: {e}", None

    # ================= 指令层 =================

    @filter.command("galnews")
    async def get_gal_news(self, event: AstrMessageEvent, game: str = ""):
        game = game.strip()
        if not game:
            yield event.plain_result("💡 请输入游戏名。")
            return

        yield event.plain_result(f"📡 正在获取《{game}》的视觉情报...")
        
        # 并发抓取
        bgm_task = self.fetch_bangumi(game)
        vndb_task = self.fetch_vndb(game)
        (bgm_txt, bgm_img), (vndb_txt, vndb_img) = await asyncio.gather(bgm_task, vndb_task)
        
        # 组装最终回复
        # 优先发 Bangumi 的图，如果没图发 VNDB 的
        final_img = bgm_img or vndb_img
        
        res_msg = (
            f"🎯【《{game}》检索报告】🎯\n\n"
            f"🔵 --- Bangumi ---\n{bgm_txt}\n\n"
            f"🔴 --- VNDB ---\n{vndb_txt}"
        )
        
        if final_img:
            # 发送带图片的消息
            yield event.chain_result([
                event.image_result(final_img),
                event.plain_result(res_msg)
            ])
        else:
            yield event.plain_result(res_msg)

    @filter.command("预约提醒")
    async def subscribe_game(self, event: AstrMessageEvent, game: str = ""):
        # ... 保持之前的订阅逻辑不变 ...
        uid = str(event.get_sender_id())
        game = game.strip()
        if not game: return
        async with self.io_lock:
            if uid not in self.subscriptions: self.subscriptions[uid] = []
            if game not in self.subscriptions[uid]:
                self.subscriptions[uid].append(game)
                await self._save_data_async()
        yield event.plain_result(f"🔔 已为《{game}》开启雷达监控！")

