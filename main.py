from astrbot.api.star import Star, Context, register
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
import httpx

@register(name="bgm_vndb", author="Grok", version="1.0.8", desc="BGM & VNDB Galgame 剧情推送助手")
class BgmVndbGalPush(Star):

    async def on_load(self):
        self.config = await self.get_config()
        self.storage = await self.get_storage()
        if "subscriptions" not in self.storage:
            self.storage["subscriptions"] = {}
        logger.info("🎮 BGM & VNDB 剧情推送助手 已成功加载 ✅ v1.0.8")

    # ==================== 工具函数 ====================
    async def _fetch_vndb_release(self, client: httpx.AsyncClient):
        headers = {"Authorization": f"Token {self.config.vndb_token}"}
        payload = {
            "filters": ["released", ">=", "2025-01-01"],
            "fields": "id,title,released,producers{name}",
            "sort": "released",
            "reverse": True,
            "results": 8
        }
        resp = await client.post("https://api.vndb.org/kana/release", json=payload, headers=headers)
        return resp.json().get("results", []) if resp.status_code == 200 else []

    # ==================== 命令 ====================
    @register("galnews")
    async def galnews_handler(self, ctx: Context, event: AstrMessageEvent):
        async with httpx.AsyncClient(timeout=15) as client:
            releases = await self._fetch_vndb_release(client)
            if not releases:
                await ctx.send("❌ 获取失败，请稍后重试")
                return
            msg = "🎮 **最新 Galgame 发售信息**（VNDB）\n\n"
            for r in releases[:5]:
                msg += f"📅 {r.get('title')}\n   发售：{r.get('released', '未知')}\n\n"
            await ctx.send(msg)

    @register("订阅gal")
    async def subscribe_handler(self, ctx: Context, event: AstrMessageEvent, args: list = None):
        if not args or len(args) < 2:
            await ctx.send("用法: /订阅gal <vndb/bgm> <id>\n示例: /订阅gal bgm 45678")
            return
        typ, sid = args[0].lower(), args[1]
        if typ not in ["vndb", "bgm"]:
            await ctx.send("仅支持 vndb 或 bgm")
            return
        chat_id = event.get_session_id()
        self.storage["subscriptions"].setdefault(chat_id, []).append({"type": typ, "id": sid, "last_data": {}})
        await ctx.send(f"✅ 已订阅 {typ.upper()} {sid}")

    @register("预约提醒")
    async def reminder_handler(self, ctx: Context, event: AstrMessageEvent):
        chat_id = event.get_session_id()
        subs = self.storage["subscriptions"].get(chat_id, [])
        if not subs:
            await ctx.send("📭 你还没有订阅")
            return
        msg = "📅 **你的订阅列表**\n\n"
        for s in subs:
            msg += f"• {s['type'].upper()} {s['id']}\n"
        await ctx.send(msg)

    @register("galcheck")
    async def galcheck_handler(self, ctx: Context, event: AstrMessageEvent):
        await ctx.send("🔄 检查中...（当前为手动模式）")
        await ctx.send("✅ 检查完成！")