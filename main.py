import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional

import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# ----------------------------- 配置 -----------------------------
BANGUMI_TOKEN = "McT3CzkJaKQs45WYRfhUU0oB8ejvE1Aj5WGYLm2J"
VNDB_API_KEY = "zkxy-bidaq-8coke-gzoy-gdem1-9zscs-kcdf"
VNDB_API_URL = "https://beta.vndb.org/api/kana"
DATA_DIR = "data/galgame_subscriber"
SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, "subscriptions.json")
CHECK_INTERVAL = 6 * 3600  # 6小时检查一次

# ----------------------------- 辅助函数 -----------------------------
def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_json(file_path: str, default=None):
    if default is None:
        default = {}
    if not os.path.exists(file_path):
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载 JSON 失败 {file_path}: {e}")
        return default

def save_json(file_path: str, data):
    ensure_data_dir()
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存 JSON 失败 {file_path}: {e}")

# ----------------------------- Bangumi 客户端 -----------------------------
class BangumiClient:
    def __init__(self, token: str):
        self.base_url = "https://api.bgm.tv/v0"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "AstrBot/GalgameHelper/1.0"
        }

    async def search_subject(self, keyword: str, limit: int = 5) -> List[Dict]:
        url = f"{self.base_url}/search/subjects"
        params = {"limit": limit}
        payload = {"keyword": keyword}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, params=params, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("data", [])
                        games = [item for item in items if item.get("type") == 4]
                        return games[:limit]
                    else:
                        logger.error(f"Bangumi 搜索失败: {resp.status}")
                        return []
            except Exception as e:
                logger.error(f"Bangumi 搜索异常: {e}")
                return []

    async def get_subject(self, subject_id: int) -> Optional[Dict]:
        url = f"{self.base_url}/subjects/{subject_id}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"获取条目失败 {subject_id}: {resp.status}")
                        return None
            except Exception as e:
                logger.error(f"获取条目异常: {e}")
                return None

# ----------------------------- VNDB 客户端 -----------------------------
class VNDBClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "Api-Key": self.api_key
        }

    async def _request(self, query: str, variables: Dict = None) -> Optional[Dict]:
        async with aiohttp.ClientSession() as session:
            payload = {"query": query}
            if variables:
                payload["variables"] = variables
            try:
                async with session.post(VNDB_API_URL, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "errors" in data:
                            logger.error(f"VNDB GraphQL 错误: {data['errors']}")
                            return None
                        return data.get("data")
                    else:
                        logger.error(f"VNDB 请求失败: {resp.status}")
                        return None
            except Exception as e:
                logger.error(f"VNDB 请求异常: {e}")
                return None

    async def search_game(self, name: str, limit: int = 5) -> List[Dict]:
        query = """
        query($search: String!, $limit: Int!) {
          search(filters: {search: $search}, first: $limit) {
            nodes { id title original released platforms description image { url } tags { name rating } externalLinks { url label } }
          }
        }
        """
        variables = {"search": name, "limit": limit}
        data = await self._request(query, variables)
        if data and "search" in data and "nodes" in data["search"]:
            return data["search"]["nodes"]
        return []

    async def get_game_details(self, vndb_id: str) -> Optional[Dict]:
        query = """
        query($id: ID!) {
          getGame(id: $id) {
            id title original released platforms description image { url }
            patches { id version released languages notes }
            extensions { id title released type }
            relations { relation game { id title } }
          }
        }
        """
        variables = {"id": vndb_id}
        data = await self._request(query, variables)
        if data and "getGame" in data:
            return data["getGame"]
        return None

# ----------------------------- 订阅管理器 -----------------------------
class SubscriptionManager:
    def __init__(self):
        self.subscriptions: Dict[str, Dict] = {}
        self.user_sub_map: Dict[str, Set[str]] = {}
        self.load()

    def load(self):
        data = load_json(SUBSCRIPTIONS_FILE, {})
        self.subscriptions = data.get("subscriptions", {})
        self.user_sub_map.clear()
        for game_key, info in self.subscriptions.items():
            for uid in info.get("subscribers", []):
                if uid not in self.user_sub_map:
                    self.user_sub_map[uid] = set()
                self.user_sub_map[uid].add(game_key)

    def save(self):
        data = {"subscriptions": self.subscriptions}
        save_json(SUBSCRIPTIONS_FILE, data)

    def add_subscription(self, user_id: str, game_key: str, game_name: str, source: str, source_id: str):
        if game_key not in self.subscriptions:
            self.subscriptions[game_key] = {
                "game_name": game_name,
                "source": source,
                "source_id": source_id,
                "subscribers": [],
                "last_state": {
                    "release_date": None,
                    "patch_count": 0,
                    "patch_versions": [],
                    "dlc_count": 0,
                    "last_notify_time": None
                }
            }
        subs = self.subscriptions[game_key]["subscribers"]
        if user_id not in subs:
            subs.append(user_id)
        if user_id not in self.user_sub_map:
            self.user_sub_map[user_id] = set()
        self.user_sub_map[user_id].add(game_key)
        self.save()

    def remove_subscription(self, user_id: str, game_key: str) -> bool:
        if game_key not in self.subscriptions:
            return False
        subs = self.subscriptions[game_key]["subscribers"]
        if user_id in subs:
            subs.remove(user_id)
            if user_id in self.user_sub_map:
                self.user_sub_map[user_id].discard(game_key)
            if not subs:
                del self.subscriptions[game_key]
            self.save()
            return True
        return False

    def get_user_subscriptions(self, user_id: str) -> List[Dict]:
        game_keys = self.user_sub_map.get(user_id, set())
        result = []
        for gk in game_keys:
            if gk in self.subscriptions:
                result.append({
                    "game_key": gk,
                    "game_name": self.subscriptions[gk]["game_name"],
                    "source": self.subscriptions[gk]["source"],
                    "source_id": self.subscriptions[gk]["source_id"]
                })
        return result

    def get_game_state(self, game_key: str) -> Dict:
        return self.subscriptions.get(game_key, {}).get("last_state", {})

    def update_game_state(self, game_key: str, new_state: Dict):
        if game_key in self.subscriptions:
            self.subscriptions[game_key]["last_state"] = new_state
            self.save()

    def get_all_subscribed_games(self) -> List[Tuple[str, Dict]]:
        return [(key, info) for key, info in self.subscriptions.items()]

# ----------------------------- 更新检测器 -----------------------------
class UpdateChecker:
    def __init__(self, bgm_client: BangumiClient, vndb_client: VNDBClient, sub_mgr: SubscriptionManager):
        self.bgm = bgm_client
        self.vndb = vndb_client
        self.sub_mgr = sub_mgr

    async def fetch_game_current_state(self, game_key: str, info: Dict) -> Dict:
        source = info["source"]
        source_id = info["source_id"]
        state = {
            "release_date": None,
            "patch_count": 0,
            "patch_versions": [],
            "dlc_count": 0,
            "dlc_names": []
        }
        if source == "bgm":
            subject = await self.bgm.get_subject(int(source_id))
            if subject:
                state["release_date"] = subject.get("date")
        elif source == "vndb":
            game = await self.vndb.get_game_details(source_id)
            if game:
                state["release_date"] = game.get("released")
                patches = game.get("patches", [])
                state["patch_count"] = len(patches)
                for p in patches:
                    state["patch_versions"].append({
                        "version": p.get("version", "未知"),
                        "date": p.get("released"),
                        "languages": p.get("languages", [])
                    })
                extensions = game.get("extensions", [])
                state["dlc_count"] = len(extensions)
                state["dlc_names"] = [ext.get("title") for ext in extensions]
        return state

    async def check_updates_for_game(self, game_key: str, info: Dict) -> Optional[List[str]]:
        old_state = self.sub_mgr.get_game_state(game_key)
        new_state = await self.fetch_game_current_state(game_key, info)
        updates = []

        # 发售日变化
        old_release = old_state.get("release_date")
        new_release = new_state.get("release_date")
        if old_release != new_release and new_release:
            if old_release:
                updates.append(f"📅 发售日变更: {old_release} → {new_release}")
            else:
                updates.append(f"🎉 发售日公布: {new_release}")

        # 补丁更新
        old_patch_count = old_state.get("patch_count", 0)
        new_patch_count = new_state.get("patch_count", 0)
        if new_patch_count > old_patch_count:
            added = new_patch_count - old_patch_count
            updates.append(f"🩹 新增 {added} 个补丁 (累计 {new_patch_count} 个)")

        # DLC 更新
        old_dlc_count = old_state.get("dlc_count", 0)
        new_dlc_count = new_state.get("dlc_count", 0)
        if new_dlc_count > old_dlc_count:
            added = new_dlc_count - old_dlc_count
            updates.append(f"💿 新增 {added} 个 DLC/扩展内容")

        # 汉化补丁检测
        old_chinese_patches = [p for p in old_state.get("patch_versions", []) if "zh" in p.get("languages", [])]
        new_chinese_patches = [p for p in new_state.get("patch_versions", []) if "zh" in p.get("languages", [])]
        if len(new_chinese_patches) > len(old_chinese_patches):
            new_ones = [p for p in new_chinese_patches if p not in old_chinese_patches]
            for p in new_ones:
                updates.append(f"🇨🇳 新增汉化补丁: {p['version']}")

        if updates:
            self.sub_mgr.update_game_state(game_key, new_state)
            game_name = info["game_name"]
            return [f"【{game_name}】"] + updates
        return []

    async def check_all_and_notify(self, context: Context):
        games = self.sub_mgr.get_all_subscribed_games()
        for game_key, info in games:
            updates = await self.check_updates_for_game(game_key, info)
            if updates:
                message = "\n".join(updates)
                for user_id in info.get("subscribers", []):
                    try:
                        chain = [Plain(f"🔔 Galgame 更新提醒\n{message}")]
                        await context.send_message(user_id, chain)
                        logger.info(f"已向 {user_id} 推送游戏 {info['game_name']} 更新")
                    except Exception as e:
                        logger.error(f"推送消息给 {user_id} 失败: {e}")

# ----------------------------- 主插件 -----------------------------
@register("bgm_vndb_galgame", "AstrBot", "Galgame 剧情推送助手 - 订阅发售日/补丁/汉化进度/DLC", "1.0.0")
class BgmVndbGalgamePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.bgm_client = BangumiClient(BANGUMI_TOKEN)
        self.vndb_client = VNDBClient(VNDB_API_KEY)
        self.sub_manager = SubscriptionManager()
        self.checker = UpdateChecker(self.bgm_client, self.vndb_client, self.sub_manager)
        # 启动后台定时任务
        asyncio.create_task(self._periodic_check())

    async def _periodic_check(self):
        while True:
            try:
                await asyncio.sleep(CHECK_INTERVAL)
                logger.info("开始执行定时更新检查...")
                await self.checker.check_all_and_notify(self.context)
            except Exception as e:
                logger.error(f"定时任务异常: {e}")

    @filter.command("galnews")
    async def galnews(self, event: AstrMessageEvent, keyword: str = None):
        """查询 Galgame 最新消息: /galnews 游戏名"""
        if not keyword:
            yield event.plain_result("❌ 请提供游戏名称，例如: /galnews 千恋万花")
            return

        bgm_results = await self.bgm_client.search_subject(keyword, limit=3)
        vndb_results = await self.vndb_client.search_game(keyword, limit=3)

        reply = f"🔍 搜索「{keyword}」的结果：\n"
        if bgm_results:
            reply += "\n【Bangumi 条目】\n"
            for idx, item in enumerate(bgm_results, 1):
                name = item.get("name", "未知")
                name_cn = item.get("name_cn", "")
                date = item.get("date", "未定")
                id_ = item.get("id")
                reply += f"{idx}. {name} {f'({name_cn})' if name_cn else ''} | 发售: {date} | bgm_id: {id_}\n"
                reply += f"   详情: https://bgm.tv/subject/{id_}\n"
        else:
            reply += "\n【Bangumi】未找到相关游戏。\n"

        if vndb_results:
            reply += "\n【VNDB 条目】\n"
            for idx, item in enumerate(vndb_results, 1):
                title = item.get("title", "未知")
                released = item.get("released", "未定")
                vid = item.get("id")
                reply += f"{idx}. {title} | 发售: {released} | vndb_id: {vid}\n"
                reply += f"   链接: https://vndb.org/{vid}\n"
        else:
            reply += "\n【VNDB】未找到相关游戏。\n"

        reply += "\n💡 使用 /subscribe bgm_{id} 或 /subscribe vndb_{id} 订阅该游戏"
        yield event.plain_result(reply)

    @filter.command("subscribe")
    async def subscribe(self, event: AstrMessageEvent, game_key: str = None):
        """订阅游戏: /subscribe bgm_123456 或 /subscribe vndb_v12345"""
        if not game_key:
            yield event.plain_result("❌ 请提供游戏标识，例如: /subscribe bgm_12345")
            return

        parts = game_key.split("_", 1)
        if len(parts) != 2 or parts[0] not in ["bgm", "vndb"]:
            yield event.plain_result("❌ 格式错误，应为 bgm_数字 或 vndb_字符串")
            return

        source, sid = parts[0], parts[1]
        user_id = event.get_sender_id()

        game_name = None
        if source == "bgm":
            subj = await self.bgm_client.get_subject(int(sid))
            if subj:
                game_name = subj.get("name_cn") or subj.get("name", sid)
        else:
            game = await self.vndb_client.get_game_details(sid)
            if game:
                game_name = game.get("title", sid)

        if not game_name:
            yield event.plain_result(f"❌ 未找到游戏信息 (ID: {sid})，请确认 ID 正确")
            return

        self.sub_manager.add_subscription(user_id, game_key, game_name, source, sid)
        yield event.plain_result(f"✅ 已订阅《{game_name}》，后续将自动推送更新通知。")

    @filter.command("unsubscribe")
    async def unsubscribe(self, event: AstrMessageEvent, game_key: str = None):
        """取消订阅: /unsubscribe bgm_123456"""
        user_id = event.get_sender_id()
        if not game_key:
            subs = self.sub_manager.get_user_subscriptions(user_id)
            if not subs:
                yield event.plain_result("📭 您尚未订阅任何游戏。")
                return
            reply = "您的订阅列表：\n"
            for idx, sub in enumerate(subs, 1):
                reply += f"{idx}. {sub['game_name']} ({sub['game_key']})\n"
            reply += "\n请使用 /unsubscribe 游戏标识 取消订阅，例如 /unsubscribe bgm_12345"
            yield event.plain_result(reply)
            return

        if self.sub_manager.remove_subscription(user_id, game_key):
            yield event.plain_result(f"✅ 已取消订阅 {game_key}")
        else:
            yield event.plain_result(f"❌ 未找到该订阅或您未订阅 {game_key}")

    @filter.command("汉化进度")
    async def hanhua(self, event: AstrMessageEvent, game_key: str = None):
        """查询汉化进度: /汉化进度 bgm_12345"""
        if not game_key:
            yield event.plain_result("❌ 请提供游戏标识，例如 /汉化进度 bgm_12345")
            return

        parts = game_key.split("_", 1)
        if len(parts) != 2 or parts[0] not in ["bgm", "vndb"]:
            yield event.plain_result("❌ 格式错误，应为 bgm_数字 或 vndb_字符串")
            return

        source, sid = parts[0], parts[1]
        reply = f"🔍 查询 {game_key} 的汉化进度：\n"
        if source == "bgm":
            reply += "Bangumi 暂无直接汉化进度字段，建议使用 VNDB ID 查询补丁。\n"
        else:
            game = await self.vndb_client.get_game_details(sid)
            if not game:
                reply += "未找到游戏信息。"
            else:
                patches = game.get("patches", [])
                chinese_patches = [p for p in patches if "zh" in p.get("languages", [])]
                if chinese_patches:
                    reply += f"已发布 {len(chinese_patches)} 个包含中文的补丁：\n"
                    for p in chinese_patches:
                        ver = p.get("version", "未知版本")
                        date = p.get("released", "未知日期")
                        reply += f"  • 版本 {ver} (发布于 {date})\n"
                else:
                    reply += "尚未发现中文补丁，汉化进度可能较低。\n"
                if patches:
                    reply += f"\n全部补丁数量: {len(patches)}"
                else:
                    reply += "\n无任何补丁记录。"
        yield event.plain_result(reply)

    @filter.command("预约提醒")
    async def upcoming(self, event: AstrMessageEvent):
        """查看即将发售的订阅游戏 (未来30天内)"""
        user_id = event.get_sender_id()
        subs = self.sub_manager.get_user_subscriptions(user_id)
        if not subs:
            yield event.plain_result("您尚未订阅任何游戏。")
            return

        now = datetime.now()
        upcoming_list = []
        for sub in subs:
            state = self.sub_manager.get_game_state(sub["game_key"])
            release_str = state.get("release_date")
            if not release_str:
                continue
            try:
                release_date = datetime.strptime(release_str, "%Y-%m-%d")
                days_left = (release_date - now).days
                if 0 <= days_left <= 30:
                    upcoming_list.append((sub["game_name"], release_date, days_left))
            except:
                pass

        if not upcoming_list:
            yield event.plain_result("📭 您订阅的游戏中暂无30日内即将发售的作品。")
            return

        reply = "📅 您订阅的游戏即将发售：\n"
        for name, rdate, days in upcoming_list:
            reply += f"• {name} - {rdate.strftime('%Y-%m-%d')} (还有 {days} 天)\n"
        yield event.plain_result(reply)

    @filter.command("list订阅")
    async def list_sub(self, event: AstrMessageEvent):
        """列出当前用户的所有订阅"""
        user_id = event.get_sender_id()
        subs = self.sub_manager.get_user_subscriptions(user_id)
        if not subs:
            yield event.plain_result("您尚未订阅任何 Galgame。")
            return
        reply = "📋 您订阅的游戏：\n"
        for idx, sub in enumerate(subs, 1):
            reply += f"{idx}. {sub['game_name']} ({sub['game_key']})\n"
        yield event.plain_result(reply)

    async def terminate(self):
        """插件卸载时保存数据"""
        self.sub_manager.save()
        logger.info("Galgame 插件已关闭")