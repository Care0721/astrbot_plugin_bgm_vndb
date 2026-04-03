from .apiclient import fetch_bangumi_subject, fetch_vndb_subject
from .datastore import (
    get_followed, add_followed, remove_followed
)
from .scheduler import start_scheduler

def setup(bot):  # 假定 astrbot 使用 setup(bot) 加载插件
    # 推送服务
    def send_func(user_id, msg):
        bot.send_private_msg(user_id, msg)

    # 启动定时任务
    start_scheduler(send_func)

    @bot.on_command("/关注gal")
    def _(event, args):
        if not args:
            return "用法: /关注gal <Bangumi subject_id>"
        gal_id = args[0]
        user_id = event.user_id
        add_followed(user_id, gal_id)
        return f"已关注 Bangumi 游戏 {gal_id}"

    @bot.on_command("/取关gal")
    def _(event, args):
        if not args:
            return "用法: /取关gal <Bangumi subject_id>"
        gal_id = args[0]
        user_id = event.user_id
        remove_followed(user_id, gal_id)
        return f"已取关 {gal_id}"

    @bot.on_command("/galnews")
    def _(event, args):
        user_id = event.user_id
        gal_ids = get_followed(user_id)
        if not gal_ids:
            return "你还没有关注任何 Bangumi 游戏。"
        msgs = []
        for gal_id in gal_ids:
            try:
                info = fetch_bangumi_subject(gal_id)
                name = info.get("name", gal_id)
                aired = info.get("date", "待定")
                summary = info.get("summary", "")
                msgs.append(f"{name} | 发售日:{aired}\n{summary}")
            except Exception:
                msgs.append(f"{gal_id} 查询失败。")
        return "\n\n".join(msgs)

    # 更多指令如 /预约提醒、/汉化进度 可仿照以上方式补充