#!/usr/bin/env python3
"""
共享工具模块
"""
import sys
from typing import List, Dict, Optional, Tuple
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from loguru import logger

# 配置常量
CDP_ENDPOINT = "http://localhost:9222"
PAGE_LOAD_TIMEOUT = 60000
PAGE_LOAD_WAIT_TIME = 5

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<g>{time:YYYY-MM-DD HH:mm:ss}</g> | <level>{level: <8}</level> | {message}",
    level="INFO"
)


async def connect_to_browser(cdp_endpoint: str = CDP_ENDPOINT) -> Tuple[Optional[Playwright], Optional[BrowserContext], Optional[Page]]:
    """
    通过 CDP 连接到本地浏览器
    
    参数:
        cdp_endpoint: CDP 端点地址
        
    返回:
        (playwright, browser_context, page) 元组，如果连接失败则返回 (None, None, None)
    """
    playwright = None
    try:
        logger.info(f"正在通过 CDP 连接到本地浏览器 ({cdp_endpoint})...")
        playwright = await async_playwright().start()
        playwright_instance = await playwright.chromium.connect_over_cdp(cdp_endpoint)
        
        if not playwright_instance.contexts:
            logger.error("浏览器没有可用的上下文")
            if playwright:
                await playwright.stop()
            return None, None, None
        
        browser_context = playwright_instance.contexts[0]
        
        # 获取现有页面或创建新页面
        valid_pages = [p for p in browser_context.pages if not p.is_closed()]
        if valid_pages:
            page = valid_pages[0]
            logger.info(f"使用现有页面，当前 URL: {page.url}")
        else:
            page = await browser_context.new_page()
            logger.info("创建新页面")
        
        page.set_default_timeout(PAGE_LOAD_TIMEOUT)
        return playwright, browser_context, page
        
    except Exception as e:
        logger.error(f"连接浏览器失败: {str(e)}")
        logger.error("请确保浏览器已启动并开启了远程调试端口: chrome --remote-debugging-port=9222")
        if playwright:
            try:
                await playwright.stop()
            except:
                pass
        return None, None, None


def validate_and_clean_models(models: List[Dict]) -> List[Dict[str, str]]:
    """
    验证和清理模型数据
    
    参数:
        models: 原始模型数据列表
        
    返回:
        清理后的模型数据列表
    """
    import re
    
    validated_models = []
    seen_models = set()
    
    for model in models:
        if not isinstance(model, dict):
            continue
        
        model_name = model.get("model", "").strip()
        model_id = model.get("id", "").strip()
        
        # 至少需要有模型名称或ID
        if not model_name and not model_id:
            continue
        
        # 使用ID作为唯一标识，如果没有ID则使用名称
        model_key = (model_id or model_name).lower()
        if not model_key or model_key in seen_models:
            continue
        seen_models.add(model_key)
        
        # 清理上下文信息（移除非数字字符，只保留数字）
        context = str(model.get("context", "")).strip()
        if context:
            # 提取数字部分
            context_match = re.search(r'(\d+)', context)
            if context_match:
                context = context_match.group(1)
            else:
                context = ""
        
        validated_models.append({
            "model": model_name or model_id,
            "id": model_id,
            "context": context
        })
    
    return validated_models
