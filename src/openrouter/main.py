#!/usr/bin/env python3
"""
从 OpenRouter RSS 页面获取模型信息
"""
import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from loguru import logger
from ..common import connect_to_browser, PAGE_LOAD_TIMEOUT, PAGE_LOAD_WAIT_TIME

# 配置常量
OPENROUTER_RSS_URL = "https://openrouter.ai/api/v1/models?use_rss=true"
# 项目根目录（src/main.py 的上一层目录）
OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "openrouter.json")


def extract_cdata_content(text: str) -> str:
    """
    从 CDATA 中提取内容
    
    参数:
        text: 可能包含 CDATA 的文本
        
    返回:
        提取的文本内容
    """
    if not text:
        return ""
    
    # 提取 CDATA 内容
    cdata_match = re.search(r'<!\[CDATA\[(.*?)\]\]>', text, re.DOTALL)
    if cdata_match:
        return cdata_match.group(1).strip()
    
    return text.strip()


def parse_rss_xml(xml_content: str) -> List[Dict[str, Any]]:
    """
    解析 RSS XML 内容，提取模型信息
    
    参数:
        xml_content: RSS XML 字符串
        
    返回:
        List[Dict]: 包含模型关键信息的列表
    """
    models = []
    seen_models = set()
    
    try:
        # 使用正则表达式提取所有 item 块
        item_pattern = r'<item>(.*?)</item>'
        item_matches = re.findall(item_pattern, xml_content, re.DOTALL)
        logger.info(f"找到 {len(item_matches)} 个模型项")
        
        for item_content in item_matches:
            try:
                # 提取 title
                title_match = re.search(r'<title>(.*?)</title>', item_content, re.DOTALL)
                title = ""
                if title_match:
                    title = extract_cdata_content(title_match.group(1))
                
                # 从 title 中提取信息，格式通常是: "提供商: 模型名称 (模型ID)"
                # 例如: "Google: Gemini 3 Flash Preview (google/gemini-3-flash-preview)"
                provider = ""
                model_name = ""
                model_id = ""
                
                if title:
                    # 解析 title 格式
                    # 匹配格式: "提供商: 模型名称 (模型ID)"
                    match = re.match(r'^([^:]+):\s*(.+?)\s*\(([^)]+)\)$', title)
                    if match:
                        provider = match.group(1).strip()
                        model_name = match.group(2).strip()
                        model_id = match.group(3).strip()
                    else:
                        # 如果没有匹配到标准格式，尝试其他格式
                        # 可能只有模型名称和ID
                        match = re.match(r'^(.+?)\s*\(([^)]+)\)$', title)
                        if match:
                            model_name = match.group(1).strip()
                            model_id = match.group(2).strip()
                        else:
                            model_name = title.strip()
                
                # 提取 description
                desc_match = re.search(r'<description>(.*?)</description>', item_content, re.DOTALL)
                description = ""
                if desc_match:
                    description = extract_cdata_content(desc_match.group(1))
                    # 移除 HTML 标签
                    description = re.sub(r'<[^>]+>', '', description)
                    description = description.strip()
                
                # 提取 link
                link_match = re.search(r'<link>(.*?)</link>', item_content, re.DOTALL)
                link = ""
                if link_match:
                    link = link_match.group(1).strip()
                
                # 从 link 中提取模型ID（如果 title 中没有）
                if not model_id and link:
                    # link 格式: https://openrouter.ai/provider/model-id
                    link_match = re.search(r'openrouter\.ai/([^/]+/[^/]+)', link)
                    if link_match:
                        model_id = link_match.group(1)
                
                # 提取 guid
                guid_match = re.search(r'<guid[^>]*>(.*?)</guid>', item_content, re.DOTALL)
                guid = ""
                if guid_match:
                    guid = guid_match.group(1).strip()
                
                # 提取 pubDate
                pub_date_match = re.search(r'<pubDate>(.*?)</pubDate>', item_content, re.DOTALL)
                pub_date = ""
                if pub_date_match:
                    pub_date = pub_date_match.group(1).strip()
                
                # 去重：使用模型ID作为唯一标识
                if not model_id:
                    # 如果没有ID，尝试从guid中提取
                    if guid:
                        # guid 格式可能是: "provider/model-id-date" 或 "provider/model-id"
                        guid_match = re.search(r'([^/]+/[^/-]+)', guid)
                        if guid_match:
                            model_id = guid_match.group(1)
                
                if not model_id:
                    continue
                
                model_key = model_id.lower()
                if model_key in seen_models:
                    continue
                seen_models.add(model_key)
                
                # 构建模型信息
                model_info = {
                    "id": model_id,
                    "name": model_name or model_id,
                }
                
                if provider:
                    model_info["provider"] = provider
                
                if description:
                    model_info["description"] = description
                
                if link:
                    model_info["link"] = link
                
                if pub_date:
                    model_info["pub_date"] = pub_date
                
                models.append(model_info)
                
            except Exception as e:
                logger.warning(f"解析模型项时出错: {str(e)}")
                continue
        
        logger.info(f"成功解析 {len(models)} 个模型")
        
    except Exception as e:
        logger.error(f"处理 RSS XML 时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []
    
    return models


async def fetch_openrouter_models() -> List[Dict[str, Any]]:
    """
    从 OpenRouter RSS 页面获取模型信息
    
    返回:
        List[Dict]: 包含模型关键信息的列表
    """
    models = []
    playwright = None
    
    try:
        # 连接到浏览器
        playwright, browser_context, page = await connect_to_browser()
        if not playwright or not browser_context or not page:
            logger.error("无法连接到浏览器，退出")
            return []
        
        logger.info(f"正在访问: {OPENROUTER_RSS_URL}")
        try:
            await page.goto(OPENROUTER_RSS_URL, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
            await asyncio.sleep(PAGE_LOAD_WAIT_TIME)  # 等待页面完全加载
        except Exception as e:
            logger.error(f"访问页面失败: {str(e)}")
            raise
        
        # 获取页面的 outerHTML
        logger.info("正在获取页面的 outerHTML...")
        outer_html = await page.evaluate("() => document.documentElement.outerHTML")
        
        if not outer_html:
            logger.error("未获取到 outerHTML")
            return []
        
        logger.debug(f"获取到 outerHTML，长度: {len(outer_html)}")
        
        # 从 outerHTML 中提取 XML 内容
        # RSS XML 可能在 <pre> 标签中，或者直接是页面的内容
        # 首先尝试查找 <pre> 标签
        pre_match = re.search(r'<pre[^>]*>(.*?)</pre>', outer_html, re.DOTALL)
        if pre_match:
            xml_content = pre_match.group(1)
            # 解码 HTML 实体
            import html
            xml_content = html.unescape(xml_content)
        else:
            # 如果没有 <pre> 标签，尝试直接提取 XML
            # 查找 <?xml 开始到 </rss> 结束的内容
            xml_match = re.search(r'<\?xml.*?</rss>', outer_html, re.DOTALL)
            if xml_match:
                xml_content = xml_match.group(0)
            else:
                # 如果都没有，尝试从 body 中提取
                body_match = re.search(r'<body[^>]*>(.*?)</body>', outer_html, re.DOTALL)
                if body_match:
                    xml_content = body_match.group(1)
                    import html
                    xml_content = html.unescape(xml_content)
                else:
                    # 最后尝试使用整个 HTML 内容
                    xml_content = outer_html
        
        # 解析 RSS XML
        models = parse_rss_xml(xml_content)
        
    except Exception as e:
        logger.error(f"获取模型信息过程中出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []
    finally:
        # 通过 CDP 连接时，只停止 playwright 实例，不关闭浏览器
        if playwright:
            try:
                await playwright.stop()
            except Exception as e:
                logger.warning(f"停止 playwright 时出错: {e}")
    
    return models


async def main():
    """OpenRouter 主函数"""
    try:
        # 从 OpenRouter API 获取模型信息
        logger.info("=" * 60)
        logger.info("开始从 OpenRouter API 获取模型信息")
        logger.info("=" * 60)
        
        try:
            models = await fetch_openrouter_models()
            
            if models:
                # 保存到 JSON 文件
                try:
                    # 构建包含链接信息的完整数据结构
                    output_data = {
                        "models_page": "https://openrouter.ai/models",
                        "api_key_page": "https://openrouter.ai/settings/keys",
                        "models": models
                    }
                    
                    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                        json.dump(output_data, f, ensure_ascii=False, indent=2)
                    logger.success(f"成功保存 {len(models)} 个模型信息到 {OUTPUT_FILE}")
                except Exception as e:
                    logger.error(f"保存文件失败: {str(e)}")
                
                # 打印统计信息
                logger.info("\n" + "=" * 60)
                logger.info("统计信息:")
                logger.info(f"  总模型数: {len(models)}")
                logger.info(f"  模型列表页: {output_data['models_page']}")
                logger.info(f"  API Key 管理页: {output_data['api_key_page']}")
                models_with_provider = sum(1 for m in models if m.get("provider"))
                models_with_description = sum(1 for m in models if m.get("description"))
                logger.info(f"  有提供商的模型: {models_with_provider}")
                logger.info(f"  有描述的模型: {models_with_description}")
                logger.info("=" * 60)
                
                # 打印前几个模型作为示例
                if models:
                    logger.info("\n前3个模型示例:")
                    for i, model in enumerate(models[:3], 1):
                        logger.info(f"\n{i}. 模型名称: {model.get('name', 'N/A')}")
                        model_id = model.get('id', '')
                        if model_id:
                            logger.info(f"   模型ID: {model_id}")
                        provider = model.get('provider')
                        if provider:
                            logger.info(f"   提供商: {provider}")
                        link = model.get('link')
                        if link:
                            logger.info(f"   链接: {link}")
            else:
                logger.warning("未获取到任何 OpenRouter 模型信息")
        except Exception as e:
            logger.error(f"获取 OpenRouter 模型失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
        
    except KeyboardInterrupt:
        logger.warning("\n用户中断程序")
        raise
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    asyncio.run(main())
