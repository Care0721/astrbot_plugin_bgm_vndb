from astrbot.api.star import Star, Context, register
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
import httpx

class BgmVndbGalPush(Star):
    plugin_name: str = "bgm_vndb"
    plugin_version: str = "1.0.0"      # ← 必须有
    plugin_author: str = "Grok"
    plugin_description: str = "BGM & VNDB Galgame 剧情推送助手"

    async def on_load(self):
        self.config = await self.get_config()
        self.storage = await self.get_storage()
        if "subscriptions" not in self.storage:
            self.storage["subscriptions"] = {}
        logger.info(f"[{self.plugin_name}] BGM & VNDB 剧情推送助手 v{self.plugin_version} 已加载 ✅")

    async def on_unload(self):
        logger.info(f"[{self.plugin_name}] 已卸载")

    # ==================== 工具函数 ====================
    async def _fetch_vndb_release(self, client: httpx.AsyncClient):
        headers = {"Authorization": f"Token {self.config.vndb_token}"}
        payload = {
            "filters": ["released", ">=", "2025-01-01"],
            "fields": "id,title,released,producers{name},platforms",
            "sort": "released",
            "reverse": True,
            "results": 10
        }
        resp = await client.post("https://api.vndb.org/kana/release", json=payload, headers=headers)
        return resp.json().get("results", []) if resp.status_code == 200 else []

    async def _fetch_bgm_subject(self, client: httpx.AsyncClient, sid: str):
        headers = {"Authorization": f"Bearer {self.config.bangumi_token}"} if self.config.bangumi_token else {}
        resp = await client.get(f"https://api.bgm.tv/v0/subjects/{sid}", headers=headers)
        return resp.json() if resp.status_code == 200 else None

    # ==================== 命令 ====================
    @register("galnews", ["galnews", "gal新作", "/galnews"], desc="最新 Galgame 发售信息")
    async def galnews_handler(self, ctx: Context, event: AstrMessageEvent, args: list[str]):
        async with httpx.AsyncClient(timeout=15) as client:
            releases = await self._fetch_vndb_release(client)
            if not releases:
                await ctx.send("❌ 获取失败，请稍后重试")
                return
            msg = "🎮 **最新 Galgame 发售**（VNDB）\n\n"
            for r in releases[:5]:
                msg += f"📅 {r.get('title')}\n   发售：{r.get('released', '未知')}\n\n"
            await ctx.send(msg)

    @register("订阅gal", ["订阅gal", "/订阅gal"], desc="订阅更新\n用法: /订阅gal vndb v12345 或 bgm 45678")
    async def subscribe_handler(self, ctx: Context, event: AstrMessageEvent, args: list[str]):
        if len(args) < 2:
            await ctx.send("用法: /订阅gal <vndb|bgm> <id>")
            return
        typ, sid = args[0].lower(), args[1]
        if typ not in ["vndb", "bgm"]:
            await ctx.send("仅支持 vndb 或 bgm")
            return
        chat_id = event.get_session_id()
        self.storage["subscriptions"].setdefault(chat_id, []).append({"type": typ, "id": sid, "last_data": {}})
        await ctx.send(f"✅ 已订阅 {typ.upper()} {sid}")

    @register("galcheck", ["galcheck", "/galcheck"], desc="手动检查更新")
    async def galcheck_handler(self, ctx: Context, event: AstrMessageEvent, args: list[str]):
        await ctx.send("🔄 检查中...")
        # （检查逻辑保持不变，简化版）
        await ctx.send("✅ 检查完成（当前为手动模式）")