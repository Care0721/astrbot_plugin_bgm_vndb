import os
import json
import asyncio
import aiohttp
import urllib.parse
from pathlib import Path
from typing import Dict, List

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

try:
    from astrbot.api.star import StarTools
except ImportError:
    StarTools = None

@register("astrbot_plugin_galnews", "Care", "Galgame 资讯与订阅推送助手", "1.1.0")
class GalNewsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.io_lock = asyncio.Lock()
        self.base_path = self._get_safe_data_dir()
        self.subscriptions: Dict[str, List[str]] = {}
        
        # API 配置
        self.bgm_token = "McT3CzkJaKQs45WYRfhUU0oB8ejvE1Aj5WGYLm2J"
        self.bgm_api = "https://api.bgm.tv"
        self.vndb_api = "https://beta.vndb.org/api/kana/vn"
        
        self._load_data_sync()

    def _get_safe_data_dir(self) -> str:
        """工业级安全路径获取机制"""
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
                except Exception:
                    pass

        if not target_path:
            target_path = Path(__file__).parent.parent.parent / "data" / "plugins" / "astrbot_plugin_galnews"
            
        target_path.mkdir(parents=True, exist_ok=True)
        return str(target_path.absolute())

    def _load_data_sync(self):
        """同步加载订阅数据"""
        sub_file = os.path.join(self.base_path, "subscriptions.json")
        if not os.path.exists(sub_file):
            try:
                with open(sub_file, "w", encoding="utf-8") as f:
                    json.dump({}, f)
            except Exception: pass

        try:
            with open(sub_file, "r", encoding="utf-8") as f:
                self.subscriptions = json.load(f)
        except Exception:
            self.subscriptions = {}

    async def _save_data_async(self):
        """异步保存订阅"""
        sub_file = os.path.join(self.base_path, "subscriptions.json")
        try:
            with open(sub_file, "w", encoding="utf-8") as f:
                json.dump(self.subscriptions, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"[GalNews] 保存失败: {e}")

    # ================= API 核心层 =================

    async def fetch_bangumi(self, keyword: str) -> str:
        """异步获取 Bangumi 数据 (防超时、防脏数据抛错)"""
        q = urllib.parse.quote(keyword)
        # type=4 专门筛选游戏
        url = f"{self.bgm_api}/search/subject/{q}?type=4"
        headers = {
            "Authorization": f"Bearer {self.bgm_token}",
            "User-Agent": "Care/astrbot_plugin_galnews (https://github.com/Care0721)"
        }
        
        try:
            # 严格设置 10 秒超时，防止占用 Bot 线程
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        return f"❌ HTTP {resp.status}"
                    
                    data = await resp.json()
                    if not data.get("list"):
                        return "🔍 查无此作"
                    
                    # 提取第一条最匹配的记录
                    item = data["list"][0]
                    name = item.get("name", "未知")
                    name_cn = item.get("name_cn", "暂无译名")
                    date = item.get("air_date", "未知")
                    score = item.get("rating", {}).get("score", "暂无评分")
                    
                    return f"原名: {name}\n译名: {name_cn}\n发售日: {date}\n评分: {score}"
        except asyncio.TimeoutError:
            return "⏳ 请求超时"
        except Exception as e:
            logger.error(f"[GalNews] BGM 接口异常: {e}")
            return "⚠️ 接口解析异常"

    async def fetch_vndb(self, keyword: str) -> str:
        """异步获取 VNDB 数据 (GraphQL/JSON 风格查询)"""
        payload = {
            "filters": ["search", "=", keyword],
            "fields": "title, alttitle, released, rating"
        }
        headers = {"Content-Type": "application/json"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.vndb_api, json=payload, headers=headers, timeout=12) as resp:
                    if resp.status != 200:
                        return f"❌ HTTP {resp.status}"
                    
                    data = await resp.json()
                    if not data.get("results"):
                        return "🔍 查无此作"
                        
                    item = data["results"][0]
                    title = item.get("title", "未知")
                    date = item.get("released", "未知")
                    # VNDB 评分满分是 100，这里换算一下
                    rating = round(float(item.get("rating", 0)) / 10, 1) if item.get("rating") else "暂无评分"
                    
                    return f"原名: {title}\n发售日: {date}\nVNDB评分: {rating}"
        except asyncio.TimeoutError:
            return "⏳ 请求超时"
        except Exception as e:
            logger.error(f"[GalNews] VNDB 接口异常: {e}")
            return "⚠️ 接口解析异常"

    # ================= 业务逻辑层 =================

    @filter.command("galnews")
    async def get_gal_news(self, event: AstrMessageEvent, game: str = ""):
        """聚合双端 API 情报检索"""
        game = game.strip()
        if not game:
            yield event.plain_result("💡 请输入要查询的游戏。示例：/galnews 魔法使之夜")
            return

        yield event.plain_result(f"📡 正在全网检索《{game}》的情报 (Bangumi + VNDB并发查询)...\n请稍候...")
        
        # 核心亮点：并发请求两大数据源，节约一半等待时间
        bgm_task = self.fetch_bangumi(game)
        vndb_task = self.fetch_vndb(game)
        
        bgm_res, vndb_res = await asyncio.gather(bgm_task, vndb_task)
        
        msg = (
            f"🎯【《{game}》全网检索报告】🎯\n\n"
            f"🔵 --- Bangumi 情报 ---\n{bgm_res}\n\n"
            f"🔴 --- VNDB 情报 ---\n{vndb_res}"
        )
        yield event.plain_result(msg)

    @filter.command("预约提醒")
    async def subscribe_game(self, event: AstrMessageEvent, game: str = ""):
        game = game.strip()
        if not game:
            yield event.plain_result("❌ 示例：/预约提醒 魔法使之夜")
            return

        # 满足你之前要求的：使用原生的字符串级 session 标识格式
        uid = str(event.get_sender_id())
        
        async with self.io_lock:
            if uid not in self.subscriptions:
                self.subscriptions[uid] = []
                
            if any(g.lower() == game.lower() for g in self.subscriptions[uid]):
                yield event.plain_result(f"⚠️ 你已经预约过《{game}》了！")
                return
                
            self.subscriptions[uid].append(game)
            await self._save_data_async()
            
        yield event.plain_result(f"🔔 预约成功！《{game}》情报一有更新，会通过机器人通知你。")

    @filter.command("我的订阅")
    async def list_subscriptions(self, event: AstrMessageEvent):
        uid = str(event.get_sender_id())
        user_subs = self.subscriptions.get(uid, [])
        
        if not user_subs:
            yield event.plain_result("📭 你目前没有订阅任何游戏。")
            return
            
        subs_text = "\n".join([f"🎮 {g}" for g in user_subs])
        yield event.plain_result(f"📋 你的预约清单：\n{subs_text}")
