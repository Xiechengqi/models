#!/usr/bin/env python3
"""
从 Nvidia Build 页面获取模型信息
"""
import asyncio
import json
import os
import re
from typing import List, Dict, Any
from loguru import logger
from ..common import connect_to_browser, PAGE_LOAD_TIMEOUT, PAGE_LOAD_WAIT_TIME

# 配置常量
NVIDIA_MODELS_URL = "https://build.nvidia.com/models"
# 项目根目录（src/main.py 的上一层目录）
OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nvidia.json")


def parse_nvidia_html(html_content: str) -> List[Dict[str, Any]]:
    """
    解析 Nvidia 模型页面 HTML，提取模型信息

    参数:
        html_content: 包含模型卡片的 HTML 内容

    返回:
        List[Dict]: 包含模型信息的列表
    """
    models = []
    seen_models = set()

    try:
        # 使用正则表达式匹配每个模型卡片
        # 卡片从 data-nvtrack-search-result-clicked 属性开始，到下一个卡片或 grid 结束
        pattern = re.compile(
            r'<div[^>]*data-nvtrack-search-result-clicked="([^"]+)"[^>]*>(.*?)(?=<div[^>]*data-nvtrack-search-result-clicked="[^"]+"[^>]*>|<div[^>]*class="grid[^>]*>)',
            re.DOTALL
        )

        matches = pattern.findall(html_content)
        logger.info(f"找到 {len(matches)} 个模型卡片")

        for model_id, card_html in matches:
            try:
                # 去重
                if model_id in seen_models:
                    continue
                seen_models.add(model_id)

                # 提取提供商
                # 格式: <a href="/provider">provider_name</a>
                provider_match = re.search(r'href="/([^"]+)"[^>]*>\s*</a>', card_html)
                provider = ""
                if provider_match:
                    provider = provider_match.group(1)
                else:
                    # 从 model_id 中提取
                    provider = model_id.split('/')[0] if '/' in model_id else ""

                # 提取模型名称
                # 优先使用 title 属性
                model_name = model_id.split('/')[-1] if '/' in model_id else model_id
                name_match = re.search(r'<a[^>]*title="([^"]+)"[^>]*data-linkbox-overlay', card_html)
                if name_match:
                    model_name = name_match.group(1)

                # 提取描述
                # 格式: <p class="...line-clamp-2...">description</p>
                desc_match = re.search(
                    r'<p[^>]*class="[^"]*line-clamp-2[^"]*"[^>]*>([^<]+)</p>',
                    card_html
                )
                description = ""
                if desc_match:
                    description = desc_match.group(1).strip()

                # 提取标签
                # 格式: <a class="...nv-tag...">tag_name</a>
                tag_matches = re.findall(
                    r'<a[^>]*class="[^"]*nv-tag[^"]*"[^>]*>([^<]+)</a>',
                    card_html
                )
                tags = [t.strip() for t in tag_matches if t.strip()]

                # 构建链接
                link = f"https://build.nvidia.com/{model_id}"

                # 构建模型信息
                model_info = {
                    "id": model_id,
                    "name": model_name,
                    "link": link,
                }

                if provider:
                    model_info["provider"] = provider

                if description:
                    model_info["description"] = description

                if tags:
                    model_info["tags"] = tags

                models.append(model_info)

            except Exception as e:
                logger.warning(f"解析模型卡片 '{model_id}' 时出错: {str(e)}")
                continue

        logger.info(f"成功解析 {len(models)} 个模型")

    except Exception as e:
        logger.error(f"处理 HTML 时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

    return models


async def fetch_nvidia_models() -> List[Dict[str, Any]]:
    """
    从 Nvidia Build 页面获取模型信息

    返回:
        List[Dict]: 包含模型信息的列表
    """
    models = []
    playwright = None

    try:
        # 连接到浏览器
        playwright, browser_context, page = await connect_to_browser()
        if not playwright or not browser_context or not page:
            logger.error("无法连接到浏览器，退出")
            return []

        logger.info(f"正在访问: {NVIDIA_MODELS_URL}")
        try:
            await page.goto(NVIDIA_MODELS_URL, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
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

        # 解析 HTML
        models = parse_nvidia_html(outer_html)

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
    """Nvidia 主函数"""
    try:
        # 从 Nvidia 页面获取模型信息
        logger.info("=" * 60)
        logger.info("开始从 Nvidia Build 页面获取模型信息")
        logger.info("=" * 60)

        try:
            models = await fetch_nvidia_models()

            if models:
                # 保存到 JSON 文件
                try:
                    # 构建包含链接信息的完整数据结构
                    output_data = {
                        "models_page": NVIDIA_MODELS_URL,
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
                models_with_provider = sum(1 for m in models if m.get("provider"))
                models_with_description = sum(1 for m in models if m.get("description"))
                models_with_tags = sum(1 for m in models if m.get("tags"))
                logger.info(f"  有提供商的模型: {models_with_provider}")
                logger.info(f"  有描述的模型: {models_with_description}")
                logger.info(f"  有标签的模型: {models_with_tags}")
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
                        description = model.get('description')
                        if description:
                            desc_preview = description[:100] + "..." if len(description) > 100 else description
                            logger.info(f"   描述: {desc_preview}")
                        tags = model.get('tags', [])
                        if tags:
                            logger.info(f"   标签: {', '.join(tags[:5])}")
                        link = model.get('link')
                        if link:
                            logger.info(f"   链接: {link}")
            else:
                logger.warning("未获取到任何 Nvidia 模型信息")
        except Exception as e:
            logger.error(f"获取 Nvidia 模型失败: {str(e)}")
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
