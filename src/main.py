#!/usr/bin/env python3
"""
主入口文件：调用各个提供商的模块
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from loguru import logger

# 导入各个提供商的模块
from src.openrouter.main import main as openrouter_main
from src.cerebras.main import main as cerebras_main
from src.modelscope.main import main as modelscope_main


async def main():
    """主函数"""
    try:
        # 抓取 OpenRouter 免费文本到文本模型信息
        logger.info("=" * 60)
        logger.info("开始抓取 OpenRouter 免费文本到文本模型信息")
        logger.info("=" * 60)
        
        try:
            await openrouter_main()
        except Exception as e:
            logger.error(f"抓取 OpenRouter 模型失败: {str(e)}")
            logger.info("继续执行其他任务...")
        
        # 抓取 Cerebras 模型列表
        logger.info("\n" + "=" * 60)
        logger.info("开始抓取 Cerebras 模型列表")
        logger.info("=" * 60)
        
        try:
            await cerebras_main()
        except Exception as e:
            logger.error(f"抓取 Cerebras 模型失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        # 抓取 ModelScope 模型列表
        logger.info("\n" + "=" * 60)
        logger.info("开始抓取 ModelScope 模型列表")
        logger.info("=" * 60)
        
        try:
            await modelscope_main()
        except Exception as e:
            logger.error(f"抓取 ModelScope 模型失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
    except KeyboardInterrupt:
        logger.warning("\n用户中断程序")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
