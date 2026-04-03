import os, json, asyncio, aiohttp, urllib.parse
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger # 使用框架建议的 logger

@register("astrbot_plugin_galnews", "Care", "Galgame 资讯助手", "1.1.5")
class GalNewsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 修复路径获取：确保传入的是字符串
        from astrbot.api.star import StarTools
        try:
            self.base_path = str(StarTools.get_data_dir())
        except:
            self.base_path = os.path.join(os.getcwd(), "data", "plugins", "galnews")
        os.makedirs(self.base_path, exist_ok=True)
        
        self.bgm_token = "McT3CzkJaKQs45WYRfhUU0oB8ejvE1Aj5WGYLm2J"
        self.vndb_token = "zkxy-bidaq-8coke-gzoy-gdem1-9zscs-kcdf"
        # 强制符合规范的 User-Agent
        self.ua = "AstrBot_Plugin_Care/1.1.5 (contact: github.com/Care0721)"

    @filter.command("monigalnews")
    async def get_gal_news(self, event: AstrMessageEvent, game: str = ""):
        if not game.strip(): return
        
        yield event.plain_result(f"📡 正在获取《{game}》的情报...")
        
        headers = {"User-Agent": self.ua, "Authorization": f"Bearer {self.bgm_token}"}
        vndb_headers = {"User-Agent": self.ua, "Authorization": f"token {self.vndb_token}", "Content-Type": "application/json"}
        
        # 增加超时和异常防护
        try:
            async with aiohttp.ClientSession() as session:
                # BGM 请求
                q = urllib.parse.quote(game)
                async with session.get(f"https://api.bgm.tv/search/subject/{q}?type=4", headers=headers, timeout=10) as r1:
                    bgm_res = await r1.json() if r1.status == 200 else None
                
                # VNDB 请求
                payload = {"filters": ["search", "=", game], "fields": "title, released, rating, image.url"}
                async with session.post("https://beta.vndb.org/api/kana/vn", headers=vndb_headers, json=payload, timeout=10) as r2:
                    vndb_res = await r2.json() if r2.status == 200 else None
                    if r2.status == 403: logger.error("VNDB 403 Forbidden - 请检查 Token 或 UA")
            
            # ... 组装逻辑 (同前) ...
            report = f"🎯【{game}】检索报告\n"
            img = None
            if bgm_res and bgm_res.get('list'):
                item = bgm_res['list'][0]
                img = item.get('images', {}).get('large')
                report += f"\n🔵 Bangumi: {item.get('name_cn') or item.get('name')}\n评分: {item.get('rating', {}).get('score') or '无'}"
            
            if vndb_res and vndb_res.get('results'):
                item = vndb_res['results'][0]
                if not img: img = item.get('image', {}).get('url')
                report += f"\n🔴 VNDB: {item.get('title')}\n评分: {item.get('rating') or '无'}"

            if img: yield event.image_result(img)
            yield event.plain_result(report)
            
        except Exception as e:
            logger.error(f"插件运行出错: {e}")
            yield event.plain_result("❌ 检索失败，请检查日志。")
