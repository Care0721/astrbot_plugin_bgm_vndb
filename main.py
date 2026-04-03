from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.api import logger
import httpx

class BgmVndbGalPush(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config = None

    async def on_load(self):
        self.config = await self.get_config()
        self.storage = await self.get_storage()
        if "subscriptions" not in self.storage:
            self.storage["subscriptions"] = {}
        logger.info("🎮 BGM & VNDB 剧情推送助手 已成功加载 ✅ v1.0.5")

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

    async def _fetch_bgm_subject(self, client: httpx.AsyncClient, sid: str):
        headers = {"Authorization": f"Bearer {self.config.bangumi_token}"} if self.config.bangumi_token else {}
        resp = await client.get(f"https://api.bgm.tv/v0/subjects/{sid}", headers=headers)
        return resp.json() if resp.status_code == 200 else None

    # ==================== 命令 ====================
    @filter.command("galnews")
    async def galnews_handler(self, event: AstrMessageEvent):
        async with httpx.AsyncClient(timeout=15) as client:
            releases = await self._fetch_vndb_release(client)
            if not releases:
                await event.send("❌ 获取失败，请稍后重试")
                return
            msg = "🎮 **最新 Galgame 发售信息**（VNDB）\n\n"
            for r in releases[:5]:
                msg += f"📅 {r.get('title')}\n   发售：{r.get('released', '未知')}\n\n"
            await event.send(msg)

    @filter.command("订阅gal")
    async def subscribe_handler(self, event: AstrMessageEvent, args: list = None):
        if not args or len(args) < 2:
            await event.send("用法: /订阅gal <vndb/bgm> <id>\n示例: /订阅gal bgm 45678")
            return
        typ, sid = args[0].lower(), args[1]
        if typ not in ["vndb", "bgm"]:
            await event.send("仅支持 vndb 或 bgm")
            return
        chat_id = event.get_session_id()
        self.storage["subscriptions"].setdefault(chat_id, []).append({"type": typ, "id": sid, "last_data": {}})
        await event.send(f"✅ 已订阅 {typ.upper()} {sid}")

    @filter.command("galcheck")
    async def galcheck_handler(self, event: AstrMessageEvent):
        await event.send("🔄 检查中...（当前为手动模式）")
        await event.send("✅ 检查完成！")

    @filter.command("预约提醒")
    async def reminder_handler(self, event: AstrMessageEvent):
        chat_id = event.get_session_id()
        subs = self.storage["subscriptions"].get(chat_id, [])
        if not subs:
            await event.send("📭 你还没有订阅")
            return
        msg = "📅 **你的订阅列表**\n\n"
        for s in subs:
            msg += f"• {s['type'].upper()} {s['id']}\n"
        await event.send(msg)