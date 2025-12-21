#!/usr/bin/env python3
"""
从 ModelScope HTML 页面获取模型列表
"""
import asyncio
import json
import os
import re
import urllib.parse
from typing import List, Dict, Any
from loguru import logger
from ..common import connect_to_browser, PAGE_LOAD_TIMEOUT, PAGE_LOAD_WAIT_TIME

# 配置常量
MODELSCOPE_BASE_URL = "https://modelscope.cn/models?filter=inference_type&sort=downloads&tabKey=task"
MODELSCOPE_PAGES = 5  # 抓取第 1-5 页
# 项目根目录（src/main.py 的上一层目录）
OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "modelscope.json")
RAW_HTML_FILE = "/tmp/modelscope.html"


def extract_model_info_from_link(link_html: str) -> Dict[str, Any]:
    """
    从 <a data-autolog...> 标签的 outerHTML 中提取模型信息
    
    参数:
        link_html: <a> 标签的完整 HTML 内容
        
    返回:
        Dict: 包含模型信息的字典
    """
    model_info = {}
    
    try:
        # 提取 href 属性
        href_match = re.search(r'href=["\']([^"\']+)["\']', link_html)
        if href_match:
            href = href_match.group(1).strip()
            # 如果是相对路径，转换为完整 URL
            if href.startswith("/models/"):
                model_info["link"] = f"https://modelscope.cn{href}"
                model_path = href.replace("/models/", "")
                model_info["id"] = model_path
                # 提取组织名称
                parts = model_path.split("/")
                if len(parts) >= 2:
                    model_info["organization"] = parts[0]
            else:
                model_info["link"] = href
        
        # 从 data-autolog 属性中提取 c4（模型 ID）
        c4_match = re.search(r'c4=([^&]+)', link_html)
        if c4_match:
            c4_encoded = c4_match.group(1)
            c4_value = urllib.parse.unquote(c4_encoded)
            # c4 格式通常是 "Organization/ModelName"
            if "/" in c4_value:
                parts = c4_value.split("/")
                if len(parts) >= 2:
                    if "organization" not in model_info:
                        model_info["organization"] = parts[0]
                    if "id" not in model_info:
                        model_info["id"] = c4_value
        
        # 优先提取中文名称作为 name
        # 查找包含 ms-title-font 类的 span 标签（通常是模型的中文名称）
        title_match = re.search(r'<span[^>]*class="[^"]*ms-title-font[^"]*"[^>]*>(.*?)</span>', link_html, re.DOTALL | re.IGNORECASE)
        if not title_match:
            # 尝试查找其他可能的标题标签
            title_match = re.search(r'<span[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</span>', link_html, re.DOTALL | re.IGNORECASE)
        if not title_match:
            title_match = re.search(r'<div[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</div>', link_html, re.DOTALL | re.IGNORECASE)
        
        if title_match:
            title_text = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
            if title_text:
                model_info["name"] = title_text
        else:
            # 如果没找到标题标签，尝试从文本中提取第一个中文短语
            all_text = re.sub(r'<[^>]+>', ' ', link_html)
            all_text = ' '.join(all_text.split())
            
            # 查找中文名称（通常是链接文本开头的第一个中文短语）
            chinese_pattern = r'[\u4e00-\u9fff]+'
            chinese_matches = re.findall(chinese_pattern, all_text)
            
            # 排除任务类型关键词
            task_keywords = [
                '文本生成图片', '文本生成视频', '视觉多模态理解', '统一多模态',
                '文本生成', '图像描述', '语音合成', '图像分类', '目标检测',
                '文本到图像', '图像到文本', '视频生成', '音频生成', '多模态理解'
            ]
            
            # 查找第一个不是任务类型关键词的中文短语作为名称
            chinese_name = None
            for chinese_text in chinese_matches:
                # 排除任务类型关键词
                if chinese_text not in task_keywords and len(chinese_text) >= 2:
                    # 检查是否在文本的开头部分（前200个字符）
                    text_pos = all_text.find(chinese_text)
                    if text_pos >= 0 and text_pos < 200:
                        chinese_name = chinese_text
                        break
            
            if chinese_name:
                model_info["name"] = chinese_name
            else:
                # 如果都没有找到，使用模型 ID 的最后一部分作为后备
                if "id" in model_info:
                    parts = model_info["id"].split("/")
                    if len(parts) >= 2:
                        model_info["name"] = parts[-1]
        
        # 查找描述信息
        desc_match = re.search(r'<div[^>]*class="[^"]*desc[^"]*"[^>]*>(.*?)</div>', link_html, re.DOTALL | re.IGNORECASE)
        if desc_match:
            desc_text = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
            if desc_text:
                model_info["description"] = desc_text
        
        # 提取时间、下载量和点赞数
        # 根据提供的 HTML 结构，这些信息在特定的 SVG 图标后面的 div 中
        
        # 1. 提取时间（在包含 icon-maasshijian-time-line1 的 SVG 后面的 div 中）
        # 格式：<use xlink:href="#icon-maasshijian-time-line1"></use></svg></span>2025.03.07</div>
        time_match = re.search(
            r'xlink:href="#icon-maasshijian-time-line1"[^>]*>.*?</use></svg></span>([^<]+)</div>',
            link_html,
            re.DOTALL | re.IGNORECASE
        )
        if not time_match:
            # 尝试更宽松的匹配
            time_match = re.search(
                r'#icon-maasshijian-time-line1"[^>]*>.*?</use>.*?</svg>.*?</span>([^<]+)</div>',
                link_html,
                re.DOTALL | re.IGNORECASE
            )
        
        if time_match:
            time_text = time_match.group(1).strip()
            if time_text:
                model_info["time"] = time_text
        
        # 2. 提取下载量（在包含 icon-maasa-zhuangtai216x16 的 SVG 后面的 div 中）
        # 格式：<use xlink:href="#icon-maasa-zhuangtai216x16"></use></svg></span>19.3k</div>
        downloads_match = re.search(
            r'xlink:href="#icon-maasa-zhuangtai216x16"[^>]*>.*?</use></svg></span>([^<]+)</div>',
            link_html,
            re.DOTALL | re.IGNORECASE
        )
        if not downloads_match:
            downloads_match = re.search(
                r'#icon-maasa-zhuangtai216x16"[^>]*>.*?</use>.*?</svg>.*?</span>([^<]+)</div>',
                link_html,
                re.DOTALL | re.IGNORECASE
            )
        
        if downloads_match:
            downloads_text = downloads_match.group(1).strip()
            if downloads_text:
                try:
                    downloads_str = downloads_text.upper()
                    # 处理 K, M, B 等单位（不区分大小写）
                    if 'K' in downloads_str:
                        downloads = int(float(downloads_str.replace('K', '').replace('k', '')) * 1000)
                    elif 'M' in downloads_str:
                        downloads = int(float(downloads_str.replace('M', '').replace('m', '')) * 1000000)
                    elif 'B' in downloads_str:
                        downloads = int(float(downloads_str.replace('B', '').replace('b', '')) * 1000000000)
                    else:
                        downloads = int(float(downloads_str))
                    model_info["downloads"] = downloads
                except (ValueError, AttributeError):
                    pass
        
        # 3. 提取点赞数/收藏数（在包含 icon-maasa-shoucangzhuangtai216x16 的 SVG 后面的 div 中）
        # 格式：<use xlink:href="#icon-maasa-shoucangzhuangtai216x16"></use></svg></span>5</div>
        stars_match = re.search(
            r'xlink:href="#icon-maasa-shoucangzhuangtai216x16"[^>]*>.*?</use></svg></span>([^<]+)</div>',
            link_html,
            re.DOTALL | re.IGNORECASE
        )
        if not stars_match:
            stars_match = re.search(
                r'#icon-maasa-shoucangzhuangtai216x16"[^>]*>.*?</use>.*?</svg>.*?</span>([^<]+)</div>',
                link_html,
                re.DOTALL | re.IGNORECASE
            )
        
        if stars_match:
            stars_text = stars_match.group(1).strip()
            if stars_text:
                try:
                    stars_str = stars_text.upper()
                    # 处理 K, M, B 等单位
                    if 'K' in stars_str:
                        stars = int(float(stars_str.replace('K', '').replace('k', '')) * 1000)
                    elif 'M' in stars_str:
                        stars = int(float(stars_str.replace('M', '').replace('m', '')) * 1000000)
                    elif 'B' in stars_str:
                        stars = int(float(stars_str.replace('B', '').replace('b', '')) * 1000000000)
                    else:
                        stars = int(float(stars_str))
                    model_info["stars"] = stars
                except (ValueError, AttributeError):
                    pass
        
        # 提取模型模态描述标签（任务类型）
        # 常见的任务类型关键词（按长度从长到短排序，优先匹配更具体的）
        # 同时支持"文字"和"文本"两种写法
        # 所有关键词都使用完全匹配，避免短关键词匹配到长关键词的一部分
        task_keywords = [
            '文字生成图片', '文本生成图片', '文字生成视频', '文本生成视频', 
            '视觉多模态理解', '统一多模态', '文本到图像', '图像到文本',
            '文字生成', '文本生成', '图像描述', '语音合成', 
            '图像分类', '目标检测', '视频生成', '音频生成', '多模态理解'
        ]
        
        task_type = None  # 只保留一个任务类型（最长的、最具体的）
        # 先提取所有文本内容，去除 HTML 标签
        all_text = re.sub(r'<[^>]+>', ' ', link_html)  # 用空格替换 HTML 标签
        all_text = ' '.join(all_text.split())  # 规范化空白字符
        
        # 使用完全匹配，按长度从长到短匹配（避免短关键词匹配到长关键词的一部分）
        # 由于关键词已按长度从长到短排序，第一个匹配到的就是最长的、最具体的
        matched_positions = set()  # 记录已匹配的位置，避免重叠
        
        for keyword in task_keywords:
            # 先查找当前关键词的所有可能匹配位置
            pattern = re.escape(keyword)
            all_matches = list(re.finditer(pattern, all_text, re.IGNORECASE))
            
            if not all_matches:
                continue
            
            # 检查是否有匹配位置在已匹配的长关键词范围内
            valid_match = None
            for match in all_matches:
                start, end = match.span()
                
                # 检查是否与已匹配的位置重叠（在已匹配范围内）
                is_in_matched_range = False
                for matched_start, matched_end in matched_positions:
                    # 如果当前匹配位置在已匹配范围内，说明是长关键词的一部分
                    if start >= matched_start and end <= matched_end:
                        is_in_matched_range = True
                        break
                
                if not is_in_matched_range:
                    # 找到了一个不在已匹配范围内的位置，检查是否是完全匹配
                    before_char = all_text[start-1] if start > 0 else ' '
                    after_char = all_text[end] if end < len(all_text) else ' '
                    
                    is_before_valid = (start == 0 or 
                                     before_char.isspace() or 
                                     before_char in '，。、；：！？' or
                                     '\u4e00' <= before_char <= '\u9fff')
                    
                    is_after_valid = (end >= len(all_text) or 
                                     after_char.isspace() or 
                                     after_char in '，。、；：！？' or
                                     '\u4e00' <= after_char <= '\u9fff')
                    
                    if is_before_valid and is_after_valid:
                        # 检查是否与已匹配位置重叠
                        overlaps = False
                        for matched_start, matched_end in matched_positions:
                            if not (end <= matched_start or start >= matched_end):
                                overlaps = True
                                break
                        
                        # 额外检查：如果短关键词紧邻长关键词，且是长关键词的一部分，应该跳过
                        # 例如："文本生成图片文本生成"中，不应该匹配"文本生成"
                        # 但如果有分隔符（空格、标点等），应该允许匹配
                        is_adjacent_to_longer = False
                        for matched_start, matched_end in matched_positions:
                            matched_text = all_text[matched_start:matched_end]
                            # 如果当前关键词是已匹配文本的一部分
                            if keyword in matched_text:
                                # 检查是否紧邻且没有分隔符
                                # 如果紧邻（相差0-1个字符），检查中间是否有分隔符
                                gap_start = min(matched_end, start)
                                gap_end = max(matched_end, start)
                                if gap_end - gap_start <= 1:
                                    # 检查中间字符是否是分隔符
                                    if gap_start < len(all_text):
                                        gap_char = all_text[gap_start:gap_end]
                                        # 如果有空格或标点，认为是分隔的，允许匹配
                                        if gap_char and (gap_char.isspace() or gap_char in '，。、；：！？'):
                                            continue  # 有分隔符，允许匹配
                                    # 没有分隔符，且是长关键词的一部分，跳过
                                    is_adjacent_to_longer = True
                                    break
                                
                                # 检查另一个方向
                                gap_start = min(matched_start, end)
                                gap_end = max(matched_start, end)
                                if gap_end - gap_start <= 1:
                                    if gap_start < len(all_text):
                                        gap_char = all_text[gap_start:gap_end]
                                        if gap_char and (gap_char.isspace() or gap_char in '，。、；：！？'):
                                            continue
                                    is_adjacent_to_longer = True
                                    break
                        
                        if not overlaps and not is_adjacent_to_longer:
                            valid_match = (start, end)
                            break
            
            if not valid_match:
                continue  # 没有找到有效的匹配位置
            
            # 使用找到的有效匹配位置（第一个匹配到的就是最长的、最具体的）
            start, end = valid_match
            matched_positions.add((start, end))
            task_type = keyword  # 只保留第一个匹配到的任务类型
            break  # 找到第一个匹配就退出，因为已经是最长的了
        
        # 如果找到了任务标签，保存到模型信息中（单个字符串，不是数组）
        if task_type:
            model_info["task_types"] = task_type
        
    except Exception as e:
        logger.warning(f"提取模型信息时出错: {str(e)}")
    
    return model_info


def parse_html_file(html_file: str) -> List[Dict[str, Any]]:
    """
    从 HTML 文件中解析模型列表
    
    参数:
        html_file: HTML 文件路径
        
    返回:
        List[Dict]: 包含模型信息的列表
    """
    models = []
    seen_models = set()
    
    try:
        logger.info(f"正在读取 HTML 文件: {html_file}")
        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        logger.info(f"HTML 文件大小: {len(html_content)} 字符")
        
        # 检查是否是模型块分隔格式（包含分隔符）
        if "<!-- ===== MODEL BLOCK SEPARATOR ===== -->" in html_content:
            # 按分隔符分割模型块
            model_blocks = html_content.split("<!-- ===== MODEL BLOCK SEPARATOR ===== -->")
            logger.info(f"检测到模型块分隔格式，找到 {len(model_blocks)} 个模型块")
        else:
            # 查找所有包含 data-autolog 和 c3=modelCard 的 <a> 标签
            link_pattern = r'<a[^>]*data-autolog[^>]*c3=modelCard[^>]*>.*?</a>'
            model_blocks = re.findall(link_pattern, html_content, re.DOTALL | re.IGNORECASE)
            logger.info(f"从 HTML 中查找模型链接，找到 {len(model_blocks)} 个模型块")
        
        for i, block_html in enumerate(model_blocks, 1):
            try:
                # 清理块内容（去除分隔符周围的空白）
                block_html = block_html.strip()
                if not block_html:
                    continue
                
                model_info = extract_model_info_from_link(block_html)
                
                # 确保至少有一个标识符
                if not model_info.get("id") and not model_info.get("name"):
                    continue
                
                # 确保有基本字段
                if not model_info.get("id"):
                    model_info["id"] = model_info.get("name", "")
                if not model_info.get("name"):
                    model_info["name"] = model_info.get("id", "")
                
                # 使用 id 作为唯一标识
                model_key = model_info.get("id", "").lower().strip()
                if not model_key or model_key in seen_models:
                    continue
                seen_models.add(model_key)
                
                models.append(model_info)
                
            except Exception as e:
                logger.warning(f"解析模型块 {i} 时出错: {str(e)}")
                continue
        
        logger.info(f"成功解析 {len(models)} 个模型")
        
    except FileNotFoundError:
        logger.error(f"HTML 文件不存在: {html_file}")
        return []
    except Exception as e:
        logger.error(f"解析 HTML 文件时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []
    
    return models


async def fetch_modelscope_models() -> List[Dict[str, Any]]:
    """
    从 ModelScope 页面获取模型信息（抓取第 1-5 页）
    
    返回:
        List[Dict]: 包含模型关键信息的列表
    """
    all_models = []
    playwright = None
    
    try:
        # 连接到浏览器
        playwright, browser_context, page = await connect_to_browser()
        if not playwright or not browser_context or not page:
            logger.error("无法连接到浏览器，退出")
            return []
        
        # 遍历第 1-5 页
        for page_num in range(1, MODELSCOPE_PAGES + 1):
            try:
                # 构建当前页的 URL
                current_url = f"{MODELSCOPE_BASE_URL}&page={page_num}"
                logger.info(f"正在访问第 {page_num} 页: {current_url}")
                
                try:
                    await page.goto(current_url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
                    await asyncio.sleep(PAGE_LOAD_WAIT_TIME)  # 等待页面完全加载
                except Exception as e:
                    logger.error(f"访问第 {page_num} 页失败: {str(e)}")
                    continue
                
                # 只在第一页切换到中文
                if page_num == 1:
                    try:
                        logger.info("正在切换到中文...")
                        clicked = await page.evaluate("""
                            () => {
                                // 方法1: 直接查找包含该 use 元素的 SVG（根据提供的元素结构）
                                const svgElement = document.querySelector('svg use[xlink\\:href="#icon-maaszhongyingzhuanhuan-CN-EN-line"]')?.closest('svg');
                                if (svgElement) {
                                    // 查找 SVG 的父元素（可能是 button、a 或其他可点击元素）
                                    let clickable = svgElement.closest('button') || 
                                                    svgElement.closest('a') || 
                                                    svgElement.closest('[role="button"]') ||
                                                    svgElement.closest('div[onclick]') ||
                                                    svgElement.closest('[data-spm-anchor-id]')?.parentElement ||
                                                    svgElement.parentElement;
                                    
                                    if (clickable) {
                                        // 尝试多种点击方式
                                        try {
                                            clickable.click();
                                            return true;
                                        } catch (e) {
                                            // 如果 click() 失败，尝试 dispatchEvent
                                            const clickEvent = new MouseEvent('click', {
                                                bubbles: true,
                                                cancelable: true,
                                                view: window
                                            });
                                            clickable.dispatchEvent(clickEvent);
                                            return true;
                                        }
                                    }
                                }
                                
                                // 方法2: 通过 use 元素向上查找可点击的父元素
                                const useElement = document.querySelector('use[xlink\\:href="#icon-maaszhongyingzhuanhuan-CN-EN-line"]');
                                if (useElement) {
                                    // 向上查找可点击的父元素（最多查找5层）
                                    let element = useElement;
                                    for (let i = 0; i < 5; i++) {
                                        element = element.parentElement;
                                        if (!element) break;
                                        
                                        // 检查是否是 button、a 或其他可点击元素
                                        if (element.tagName === 'BUTTON' || 
                                            element.tagName === 'A' || 
                                            element.getAttribute('role') === 'button' ||
                                            element.onclick ||
                                            element.getAttribute('data-spm-anchor-id') ||
                                            element.style.cursor === 'pointer') {
                                            try {
                                                element.click();
                                                return true;
                                            } catch (e) {
                                                const clickEvent = new MouseEvent('click', {
                                                    bubbles: true,
                                                    cancelable: true,
                                                    view: window
                                                });
                                                element.dispatchEvent(clickEvent);
                                                return true;
                                            }
                                        }
                                    }
                                }
                                
                                // 方法3: 查找所有包含该图标的 SVG，尝试点击
                                const allSvgs = document.querySelectorAll('svg');
                                for (let svg of allSvgs) {
                                    const use = svg.querySelector('use[xlink\\:href="#icon-maaszhongyingzhuanhuan-CN-EN-line"]');
                                    if (use) {
                                        // 尝试点击 SVG 或其父元素
                                        let clickable = svg.closest('button') || 
                                                        svg.closest('a') || 
                                                        svg.closest('[role="button"]') ||
                                                        svg.closest('div[onclick]') ||
                                                        svg.closest('[data-spm-anchor-id]')?.parentElement ||
                                                        svg.parentElement;
                                        if (clickable) {
                                            try {
                                                clickable.click();
                                                return true;
                                            } catch (e) {
                                                const clickEvent = new MouseEvent('click', {
                                                    bubbles: true,
                                                    cancelable: true,
                                                    view: window
                                                });
                                                clickable.dispatchEvent(clickEvent);
                                                return true;
                                            }
                                        }
                                        // 如果找不到父元素，直接点击 SVG
                                        try {
                                            svg.click();
                                            return true;
                                        } catch (e) {
                                            const clickEvent = new MouseEvent('click', {
                                                bubbles: true,
                                                cancelable: true,
                                                view: window
                                            });
                                            svg.dispatchEvent(clickEvent);
                                            return true;
                                        }
                                    }
                                }
                                
                                return false;
                            }
                        """)
                        
                        if clicked:
                            logger.info("已点击语言切换按钮，等待页面切换...")
                            await asyncio.sleep(2)  # 等待语言切换完成
                        else:
                            logger.warning("未找到语言切换按钮，继续执行...")
                    except Exception as e:
                        logger.warning(f"切换语言时出错: {str(e)}，继续执行...")
                
                # 等待模型列表加载
                try:
                    await page.wait_for_selector('a[data-autolog*="c3=modelCard"]', timeout=15000)
                    logger.debug(f"第 {page_num} 页找到模型卡片链接")
                except Exception as e:
                    logger.warning(f"第 {page_num} 页未找到模型卡片: {str(e)}，继续执行...")
                
                # 获取当前页所有模型卡片的 outerHTML
                logger.info(f"正在获取第 {page_num} 页所有模型卡片的 outerHTML...")
                model_blocks = await page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a[data-autolog*="c3=modelCard"]');
                        const blocks = [];
                        links.forEach(link => {
                            blocks.push(link.outerHTML);
                        });
                        return blocks;
                    }
                """)
                
                if not model_blocks or len(model_blocks) == 0:
                    logger.warning(f"第 {page_num} 页未获取到任何模型卡片")
                    continue
                
                logger.info(f"第 {page_num} 页找到 {len(model_blocks)} 个模型卡片，开始提取信息...")
                
                # 从当前页的模型块中提取信息
                page_models = []
                for i, block_html in enumerate(model_blocks, 1):
                    try:
                        logger.debug(f"正在处理第 {page_num} 页第 {i}/{len(model_blocks)} 个模型卡片...")
                        
                        # 从 outerHTML 中提取模型信息
                        model_info = extract_model_info_from_link(block_html)
                        
                        # 确保至少有一个标识符
                        if not model_info.get("id") and not model_info.get("name"):
                            logger.debug(f"第 {page_num} 页模型卡片 {i} 缺少标识符，跳过")
                            continue
                        
                        # 确保有基本字段
                        if not model_info.get("id"):
                            model_info["id"] = model_info.get("name", "")
                        if not model_info.get("name"):
                            model_info["name"] = model_info.get("id", "")
                        
                        page_models.append(model_info)
                        
                    except Exception as e:
                        logger.warning(f"处理第 {page_num} 页模型卡片 {i} 时出错: {str(e)}")
                        continue
                
                logger.info(f"第 {page_num} 页成功提取了 {len(page_models)} 个模型")
                all_models.extend(page_models)
                
            except Exception as e:
                logger.error(f"处理第 {page_num} 页时出错: {str(e)}")
                continue
        
        # 去重：使用 id 作为唯一标识
        seen_models = set()
        unique_models = []
        for model_info in all_models:
            model_key = model_info.get("id", "").lower().strip()
            if model_key and model_key not in seen_models:
                seen_models.add(model_key)
                unique_models.append(model_info)
            elif not model_key:
                # 如果没有 id，也添加（可能是异常情况）
                unique_models.append(model_info)
        
        logger.info(f"总共从 {MODELSCOPE_PAGES} 页中提取了 {len(unique_models)} 个唯一模型（去重前: {len(all_models)} 个）")
        
        return unique_models
        
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
    
    return []


async def main():
    """ModelScope 主函数"""
    try:
        # 从 ModelScope 页面获取模型信息
        logger.info("=" * 60)
        logger.info("开始从 ModelScope 获取模型信息")
        logger.info("=" * 60)
        
        try:
            models = await fetch_modelscope_models()
            
            if models:
                # 保存到 JSON 文件
                try:
                    # 构建包含链接信息的完整数据结构
                    output_data = {
                        "models_page": "https://modelscope.cn/models",
                        "api_key_page": "https://modelscope.cn/my/myaccesstoken",
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
                models_with_org = sum(1 for m in models if m.get("organization"))
                models_with_description = sum(1 for m in models if m.get("description"))
                logger.info(f"  有组织的模型: {models_with_org}")
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
                        org = model.get('organization')
                        if org:
                            logger.info(f"   组织: {org}")
                        link = model.get('link')
                        if link:
                            logger.info(f"   链接: {link}")
            else:
                logger.warning("未获取到任何 ModelScope 模型信息")
        except Exception as e:
            logger.error(f"获取 ModelScope 模型失败: {str(e)}")
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
