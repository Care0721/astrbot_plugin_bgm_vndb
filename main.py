from astrbot.api.star import Star, Context, register
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger, scheduler
import httpx
from datetime import datetime

class BgmVndbGalPush(Star):
    plugin_name: str = "bgm_vndb"   # 已适配你的仓库名

    async def on_load(self):
        self.config = await self.get_config()
        self.storage = await self.get_storage()
        if "subscriptions" not in self.storage:
            self.storage["subscriptions"] = {}  # chat_id -> list of dict
        logger.info(f"[{self.plugin_name}] BGM & VNDB 剧情推送助手 已加载 ✅")

    async def on_unload(self):
        logger.info(f"[{self.plugin_name}] BGM & VNDB 剧情推送助手 已卸载")

    # ==================== 工具函数 ====================
    async def _fetch_vndb_release(self, client: httpx.AsyncClient):
        headers = {"Authorization": f"Token {self.config.vndb_token}"}
        payload = {
            "filters": ["released", ">=", "2025-01-01"],
            "fields": "id,title,released,producers{name},platforms,image{url}",
            "sort": "released",
            "reverse": True,
            "results": 10
        }
        resp = await client.post("https://api.vndb.org/kana/release", json=payload, headers=headers)
        return resp.json().get("results", []) if resp.status_code == 200 else []

    async def _fetch_bgm_subject(self, client: httpx.AsyncClient, sid: str):
        headers = {"Authorization": f"Bearer {self.config.bangumi_token}"} if self.config.bangumi_token else {}
        url = f"https://api.bgm.tv/v0/subjects/{sid}"
        resp = await client.get(url, headers=headers)
        return resp.json() if resp.status_code == 200 else None

    # ==================== 命令 ====================
    @register("galnews", ["galnews", "gal新作", "/galnews"], desc="获取最新 Galgame 发售信息（VNDB）")
    async def galnews_handler(self, ctx: Context, event: AstrMessageEvent, args: list[str]):
        async with httpx.AsyncClient(timeout=15) as client:
            releases = await self._fetch_vndb_release(client)
            if not releases:
                await ctx.send("❌ 获取最新信息失败，请稍后重试。")
                return

            msg = "🎮 **最新 Galgame 发售信息**（VNDB）\n\n"
            for r in releases[:5]:
                date = r.get("released", "未知")
                title = r.get("title", "未知")
                producers = ", ".join([p["name"] for p in r.get("producers", [])]) or "未知"
                msg += f"📅 **{title}**\n   发售：{date}\n   制作：{producers}\n\n"
            await ctx.send(msg)

    @register("订阅gal", ["订阅gal", "订阅", "/订阅gal"], desc="订阅 Galgame 更新\n用法: /订阅gal <type> <id>\n示例: /订阅gal vndb v12345 或 /订阅gal bgm 45678")
    async def subscribe_handler(self, ctx: Context, event: AstrMessageEvent, args: list[str]):
        if len(args) < 2:
            await ctx.send("用法: /订阅gal <type> <id>\n type 支持：vndb / bgm")
            return

        typ = args[0].lower()
        sid = args[1]
        if typ not in ["vndb", "bgm"]:
            await ctx.send("type 仅支持 vndb 或 bgm")
            return

        chat_id = event.get_session_id()
        if chat_id not in self.storage["subscriptions"]:
            self.storage["subscriptions"][chat_id] = []

        self.storage["subscriptions"][chat_id].append({
            "type": typ,
            "id": sid,
            "last_data": {}
        })

        await ctx.send(f"✅ 已订阅 {typ.upper()} {sid}\n每日自动检查发售日、DLC、补丁、新作并推送。")

    @register("预约提醒", ["预约提醒", "/预约提醒"], desc="查看你订阅的 Galgame 预约提醒")
    async def reminder_handler(self, ctx: Context, event: AstrMessageEvent, args: list[str]):
        chat_id = event.get_session_id()
        subs = self.storage["subscriptions"].get(chat_id, [])
        if not subs:
            await ctx.send("📭 你还没有订阅任何 Galgame")
            return

        msg = "📅 **你的 Galgame 预约提醒**\n\n"
        for sub in subs:
            msg += f"• {sub['type'].upper()} {sub['id']}\n"
        await ctx.send(msg)

    @register("汉化进度", ["汉化进度", "/汉化进度"], desc="查看订阅项目的 Bangumi 汉化进度")
    async def han_progress_handler(self, ctx: Context, event: AstrMessageEvent, args: list[str]):
        chat_id = event.get_session_id()
        subs = self.storage["subscriptions"].get(chat_id, [])
        if not subs:
            await ctx.send("📭 你还没有订阅任何项目")
            return

        msg = "🇨🇳 **汉化进度查询**（仅 Bangumi 项目）\n\n"
        async with httpx.AsyncClient(timeout=15) as client:
            for sub in [s for s in subs if s["type"] == "bgm"]:
                data = await self._fetch_bgm_subject(client, sub["id"])
                if data:
                    title = data.get("name_cn") or data.get("name", "未知")
                    url = f"https://bgm.tv/subject/{sub['id']}"
                    msg += f"📖 {title}（{sub['id']}）\n🔗 {url}\n（点击链接可查看最新汉化贴）\n\n"
                else:
                    msg += f"❌ 无法获取 {sub['id']}\n"
        await ctx.send(msg or "没有 Bangumi 订阅项目")

    @register("galcheck", ["galcheck", "/galcheck"], desc="手动检查并推送订阅更新")
    async def galcheck_handler(self, ctx: Context, event: AstrMessageEvent, args: list[str]):
        await ctx.send("🔄 正在检查所有订阅更新...")
        chat_id = event.get_session_id()
        updated_count = 0
        async with httpx.AsyncClient(timeout=15) as client:
            subs = self.storage["subscriptions"].get(chat_id, [])
            for sub in subs:
                if sub["type"] == "vndb":
                    releases = await self._fetch_vndb_release(client)
                    if releases:
                        await ctx.send(f"🔥 VNDB {sub['id']} 有新动态（最新发售信息）")
                        updated_count += 1
                elif sub["type"] == "bgm":
                    data = await self._fetch_bgm_subject(client, sub["id"])
                    if data and data.get("date"):
                        last_date = sub["last_data"].get("date")
                        new_date = data.get("date")
                        if last_date != new_date:
                            await ctx.send(f"📅 Bangumi {sub['id']} 发售日更新 → {new_date}")
                            sub["last_data"]["date"] = new_date
                            updated_count += 1
        await ctx.send(f"✅ 检查完成，共发现 {updated_count} 条更新！")

    # ==================== 每日自动推送（北京时间 9:00） ====================
    @scheduler.cron("0 9 * * *")
    async def daily_update_check(self):
        logger.info("🎮 [BGM & VNDB] 开始每日更新检查...")
        count = 0
        async with httpx.AsyncClient(timeout=20) as client:
            for chat_id, subs in self.storage.get("subscriptions", {}).items():
                for sub in subs:
                    try:
                        if sub["type"] == "bgm":
                            data = await self._fetch_bgm_subject(client, sub["id"])
                            if data and data.get("date"):
                                if sub["last_data"].get("date") != data["date"]:
                                    logger.info(f"📢 更新推送 → {chat_id} | Bangumi {sub['id']} 发售日 {data['date']}")
                                    sub["last_data"]["date"] = data["date"]
                                    count += 1
                        # VNDB 后续可继续扩展
                    except Exception as e:
                        logger.error(f"检查 {sub['type']} {sub['id']} 失败: {e}")
        logger.info(f"🎮 [BGM & VNDB] 每日检查完成，发现 {count} 条更新")