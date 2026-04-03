from apscheduler.schedulers.background import BackgroundScheduler
from .datastore import load_db
from .apiclient import fetch_bangumi_subject
import time

def start_scheduler(send_func):
    scheduler = BackgroundScheduler()

    def job():
        db = load_db()
        for user_id, galgames in db.items():
            for gal_id in galgames:
                info = fetch_bangumi_subject(gal_id)
                # 推送示例消息
                msg = f"[{info.get('name', gal_id)}] 最新状态: {info.get('infobox', '暂无更新')}"
                send_func(user_id, msg)
                time.sleep(1)
    
    scheduler.add_job(job, "interval", hours=12)
    scheduler.start()