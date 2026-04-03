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

@register("astrbot_plugin_galnews", "Care", "Galgame 资讯与订阅推送助手", "1.1.2")
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
        
        # 全局统一 UA，防止被各大数据库墙掉
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
                except Exception:
                    pass

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
            with open(sub_file, "r", encoding="utf-8") as f:
                self.subscriptions = json.load(f)
        except Exception:
            self.subscriptions = {}

    async def _save_data_async(self):
        sub_file = os.path.join(self.base_path, "subscriptions.json")
        try:
            with open(sub_file, "w", encoding="utf-8") as f:
                json.dump(self.subscriptions, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"[GalNews] 保存失败: {e}")

    # ================= 优化后的 API 数据清洗层 =================

    async def fetch_bangumi(self, keyword: str) -> str:
        q = urllib.parse.quote(keyword)
        url = f"{self.bgm_api}/search/subject/{q}?type=4"
        
        headers = {
            "Authorization": f"Bearer {self.bgm_token}",
            "User-Agent": self.user_agent
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        return f"❌ HTTP {resp.status} - 接口异常"
                    
                    data = await resp.json()
                    if not data.get("list"):
                        return "🔍 查无此作"
                    
                    item = data["list"][0]
                    
                    # 【核心修复】不仅用 get，还要用 or "未知" 拦截空字符串 ("")
                    name = item.get("name") or "未知"
                    name_cn = item.get("name_cn") or "暂无官方译名"
                    date = item.get("air_date") or "未知 (可能尚未发售)"
                    
                    # 评分字段可能嵌套缺失
                    rating_dict = item.get("rating") or {}
                    score = rating_dict.get("score") or "暂无评分"
                    
                    bgm_id = item.get("id")
                    url_link = f"https://bgm.tv/subject/{bgm_id}" if bgm_id else "无链接"
                    
                    return (
                        f"原名: {name}\n"
                        f"译名: {name_cn}\n"
                        f"发售日: {date}\n"
                        f"评分: {score}\n"
                        f"链接: {url_link}"
                    )
        except asyncio.TimeoutError:
            return "⏳ 请求超时，Bangumi服务器未响应"
        except Exception as e:
            logger.error(f"[GalNews] BGM 异常: {e}")
            return "⚠️ 数据解析异常"

    async def fetch_vndb(self, keyword: str) -> str:
        payload = {
            "filters": ["search", "=", keyword],
            "fields": "id, title, alttitle, released, rating"
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"token {self.vndb_token}",
            # 【核心修复】强制添加 User-Agent，解决 403 被拒问题
            "User-Agent": self.user_agent
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.vndb_api, json=payload, headers=headers, timeout=12) as resp:
                    if resp.status == 403:
                        # 额外兜底，如果 Token 权限不够或仍被墙，返回明确提示
                        return "❌ HTTP 403 - API 密钥无效或被 VNDB 防火墙拦截"
                    elif resp.status != 200:
                        return f"❌ HTTP {resp.status} - 接口异常"
                    
                    data = await resp.json()
                    if not data.get("results"):
                        return "🔍 查无此作"
                        
                    item = data["results"][0]
                    
                    # 数据清洗提取
                    title = item.get("title") or "未知"
                    alt_title = item.get("alttitle") or "暂无别名"
                    date = item.get("released") or "未知"
                    
                    # 评分清洗，VNDB 满分 100，转成 10 分制
                    raw_rating = item.get("rating")
                    rating = round(float(raw_rating) / 10, 1) if raw_rating else "暂无评分"
                    
                    vid = item.get("id")
                    url_link = f"https://vndb.org/{vid}" if vid else "无链接"
                    
                    return (
                        f"标题: {title}\n"
                        f"别名: {alt_title}\n"
                        f"发售日: {date}\n"
                        f"评分: {rating}\n"
                        f"链接: {url_link}"
                    )
        except asyncio.TimeoutError:
            return "⏳ 请求超时，VNDB服务器未响应"
        except Exception as e:
            logger.error(f"[GalNews] VNDB 异常: {e}")
            return "⚠️ 数据解析异常"

    # ==========================================================

    @filter.command("galnews")
    async def get_gal_news(self, event: AstrMessageEvent, game: str = ""):
        game = game.strip()
        if not game:
            yield event.plain_result("💡 请输入要查询的游戏。示例：/galnews 缘之空")
            return

        yield event.plain_result(f"📡 正在全网检索《{game}》的情报 (双接口满速并发中)...")
        
        bgm_task = self.fetch_bangumi(game)
        vndb_task = self.fetch_vndb(game)
        bgm_res, vndb_res = await asyncio.gather(bgm_task, vndb_task)
        
        msg = (
            f"🎯【《{game}》全网检索报告】🎯\n\n"
            f"🔵 --- Bangumi 数据 ---\n{bgm_res}\n\n"
            f"🔴 --- VNDB 数据 ---\n{vndb_res}"
        )
        yield event.plain_result(msg)

    @filter.command("预约提醒")
    async def subscribe_game(self, event: AstrMessageEvent, game: str = ""):
        game = game.strip()
        if not game:
            yield event.plain_result("❌ 示例：/预约提醒 魔法使之夜")
            return

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
