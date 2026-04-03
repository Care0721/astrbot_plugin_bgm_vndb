"""
Galgame 剧情推送助手插件
自动订阅关注的 Galgame 更新，推送发售日、补丁、汉化进度、DLC、新作消息
"""

from .main import GalNewsPlugin

async def initialize(ctx, config):
    """插件初始化"""
    plugin = GalNewsPlugin(ctx, config)
    await plugin.setup()
    return plugin