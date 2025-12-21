#!/usr/bin/env python3
"""
从 Cerebras 文档页面抓取模型列表
"""
import asyncio
import json
import os
import re
from typing import List, Dict
from loguru import logger
from ..common import connect_to_browser, PAGE_LOAD_TIMEOUT, PAGE_LOAD_WAIT_TIME

# 配置常量
CEREBRAS_URL = "https://inference-docs.cerebras.ai/models/overview"
# 项目根目录（src/main.py 的上一层目录）
OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CEREBRAS_MODELS_FILE = os.path.join(OUTPUT_DIR, "cerebras.json")


async def scrape_cerebras_models() -> List[Dict[str, str]]:
    """
    从 Cerebras 文档页面抓取模型列表
    
    返回:
        List[Dict]: 包含模型名称和ID的列表
    """
    models = []
    playwright = None
    
    try:
        # 连接到浏览器
        playwright, browser_context, page = await connect_to_browser()
        if not playwright or not browser_context or not page:
            logger.error("无法连接到浏览器，退出")
            return []
        
        logger.info(f"正在访问: {CEREBRAS_URL}")
        try:
            await page.goto(CEREBRAS_URL, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
            await asyncio.sleep(PAGE_LOAD_WAIT_TIME)  # 等待页面完全加载
        except Exception as e:
            logger.error(f"访问页面失败: {str(e)}")
            raise
        
        # 等待表格加载
        try:
            await page.wait_for_selector("table tbody tr", timeout=15000)
            logger.debug("找到表格行")
        except Exception as e:
            logger.warning(f"未找到表格: {str(e)}，继续执行...")
        
        # 获取 body 标签的 outerHTML
        logger.info("正在获取 body 标签的 outerHTML...")
        body_outer_html = await page.evaluate("() => document.body.outerHTML")
        
        if not body_outer_html:
            logger.error("未获取到 body outerHTML")
            return []
        
        logger.debug(f"获取到 body outerHTML，长度: {len(body_outer_html)}")
        
        # 提取所有表格（table 标签）
        table_pattern = r'<table[^>]*>(.*?)</table>'
        table_matches = re.findall(table_pattern, body_outer_html, re.DOTALL)
        
        if not table_matches:
            logger.warning("在 body outerHTML 中未找到 table 标签")
            return []
        
        logger.info(f"找到 {len(table_matches)} 个表格")
        
        seen_models = set()
        
        # 遍历所有表格
        for table_content in table_matches:
            # 检查 thead 中是否包含 "Hugging Face Link"
            thead_match = re.search(r'<thead[^>]*>(.*?)</thead>', table_content, re.DOTALL)
            if not thead_match:
                continue
            
            thead_content = thead_match.group(1)
            # 检查是否包含 "Hugging Face Link" 或 "Hugging Face" 相关文本
            if not re.search(r'Hugging\s+Face\s+Link', thead_content, re.IGNORECASE):
                logger.debug("跳过不包含 'Hugging Face Link' 列的表格")
                continue
            
            logger.debug("找到包含 'Hugging Face Link' 列的表格")
            
            # 提取 tbody 内容
            tbody_match = re.search(r'<tbody[^>]*>(.*?)</tbody>', table_content, re.DOTALL)
            if not tbody_match:
                continue
            
            tbody_content = tbody_match.group(1)
            
            # 提取所有 tr 标签
            tr_pattern = r'<tr[^>]*>(.*?)</tr>'
            tr_matches = re.findall(tr_pattern, tbody_content, re.DOTALL)
            
            for tr_content in tr_matches:
                try:
                    # 提取所有 td 标签
                    td_pattern = r'<td[^>]*>(.*?)</td>'
                    td_matches = re.findall(td_pattern, tr_content, re.DOTALL)
                    
                    if len(td_matches) < 2:
                        continue
                    
                    # 第一列：模型ID（在 <code> 标签中）
                    model_id = ""
                    code_match = re.search(r'<code>(.*?)</code>', td_matches[0], re.DOTALL)
                    if code_match:
                        model_id = code_match.group(1).strip()
                    else:
                        # 如果没有 code 标签，尝试直接提取文本
                        # 移除所有 HTML 标签
                        model_id = re.sub(r'<[^>]+>', '', td_matches[0]).strip()
                    
                    if not model_id:
                        continue
                    
                    # 第二列：精度信息（FP16, FP16/FP8等）
                    precision = ""
                    if len(td_matches) >= 2:
                        # 移除 HTML 标签，但保留文本内容
                        precision = re.sub(r'<[^>]+>', '', td_matches[1]).strip()
                    
                    # 第三列：链接（Hugging Face Link）
                    link = ""
                    if len(td_matches) >= 3:
                        link_match = re.search(r'<a[^>]*href=["\']([^"\']+)["\']', td_matches[2])
                        if link_match:
                            link = link_match.group(1).strip()
                    
                    # 只保存有链接的模型（确保是 Hugging Face Link 列中的模型）
                    if not link:
                        logger.debug(f"跳过没有链接的模型: {model_id}")
                        continue
                    
                    # 去重：使用模型ID作为唯一标识
                    model_key = model_id.lower().strip()
                    if model_key and model_key not in seen_models:
                        seen_models.add(model_key)
                        
                        model_info = {
                            "id": model_id,
                            "name": model_id  # 默认使用ID作为名称
                        }
                        
                        if precision:
                            model_info["precision"] = precision
                        
                        if link:
                            model_info["link"] = link
                        
                        models.append(model_info)
                        
                except Exception as e:
                    logger.warning(f"解析行数据时出错: {str(e)}")
                    continue
        
        logger.info(f"成功提取 {len(models)} 个模型")
        
    except Exception as e:
        logger.error(f"抓取 Cerebras 模型列表时出错: {str(e)}")
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
    """Cerebras 主函数"""
    try:
        # 抓取 Cerebras 模型列表
        logger.info("=" * 60)
        logger.info("开始抓取 Cerebras 模型列表")
        logger.info("=" * 60)
        
        try:
            cerebras_models = await scrape_cerebras_models()
            
            if cerebras_models:
                try:
                    # 构建包含链接信息的完整数据结构
                    output_data = {
                        "models_page": "https://inference-docs.ai/models/overview",
                        "api_key_page": "https://cloud.cerebras.ai/platform",
                        "models": cerebras_models
                    }
                    
                    with open(CEREBRAS_MODELS_FILE, "w", encoding="utf-8") as f:
                        json.dump(output_data, f, ensure_ascii=False, indent=2)
                    
                    logger.success(f"成功保存 {len(cerebras_models)} 个 Cerebras 模型信息到 {CEREBRAS_MODELS_FILE}")
                    
                    # 打印统计信息
                    logger.info("\n" + "=" * 60)
                    logger.info("统计信息:")
                    logger.info(f"  总模型数: {len(cerebras_models)}")
                    logger.info(f"  模型列表页: {output_data['models_page']}")
                    logger.info(f"  API Key 管理页: {output_data['api_key_page']}")
                    logger.info("=" * 60)
                    
                    # 打印前几个模型作为示例
                    if cerebras_models:
                        logger.info("\n前3个 Cerebras 模型示例:")
                        for i, model in enumerate(cerebras_models[:3], 1):
                            logger.info(f"\n{i}. 模型ID: {model.get('id', 'N/A')}")
                            precision = model.get('precision')
                            if precision:
                                logger.info(f"   精度: {precision}")
                            link = model.get('link')
                            if link:
                                logger.info(f"   Hugging Face 链接: {link}")
                except Exception as e:
                    logger.error(f"保存 Cerebras 模型文件失败: {str(e)}")
            else:
                logger.warning("未提取到 Cerebras 模型数据")
        except Exception as e:
            logger.error(f"抓取 Cerebras 模型失败: {str(e)}")
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
