"""
插件主程序
"""
import asyncio
from handlers.gal_news import GalNewsHandler
from handlers.preorder import PreorderHandler
from handlers.patch_progress import PatchProgressHandler
from scheduler.task_scheduler import TaskScheduler
from apis.storage import StorageManager


class GalNewsPlugin:
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config
        self.storage = StorageManager()
        self.scheduler = TaskScheduler()
        
        # 初始化处理器
        self.gal_news = GalNewsHandler(ctx, config)
        self.preorder = PreorderHandler(ctx, config, self.storage)
        self.patch_progress = PatchProgressHandler(ctx, config)

    async def setup(self):
        """插件启动"""
        # 注册命令
        self.ctx.add_command(
            name="galnews",
            handler=self.gal_news.handle,
            help_text="查看最新 Galgame 动态"
        )
        
        self.ctx.add_command(
            name="预约提醒",
            handler=self.preorder.handle,
            help_text="管理 Galgame 预约提醒"
        )
        
        self.ctx.add_command(
            name="汉化进度",
            handler=self.patch_progress.handle,
            help_text="查看 Galgame 汉化翻译进度"
        )
        
        # 启动定时任务
        await self.scheduler.start(self)

    async def shutdown(self):
        """插件关闭"""
        await self.scheduler.stop()