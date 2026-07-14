"""
LLM 获取选中文字功能

功能：
1. 获取当前剪贴板内容（用于还原）
2. 模拟 Ctrl+C 复制选中的文字
3. 读取新的剪贴板内容
4. 还原原来的剪贴板内容
5. 判断内容是否变化，返回选中的文字
"""
import time
import pyclip
import keyboard
from . import logger
from .llm_clipboard import safe_paste


# 全局变量：记录每个角色最后一次使用的选中文字
_last_selection_by_role = {}


def get_selected_text(role_config, state) -> str:
    """
    获取用户当前选中的文字（通过模拟 Ctrl+C）

    Args:
        role_config: 角色配置 RoleConfig 对象

    Returns:
        选中的文字，如果不应该使用则返回空字符串
    """
    global _last_selection_by_role

    # 检查是否启用获取选中文字
    if not role_config.enable_read_selection:
        return ""

    role_name = role_config.name
    original_clipboard = ""

    try:
        # 保存当前剪贴板内容
        original_clipboard = safe_paste()

        # 先写入唯一标记，避免“选中文字与原剪贴板相同”时被误判为没有选区
        clipboard_marker = f"__CAPSWRITER_SELECTION_{time.time_ns()}__"
        pyclip.copy(clipboard_marker)

        # 模拟 Ctrl+C 复制选中的文字
        keyboard.press_and_release('ctrl+c')

        # 浏览器复制整页可能异步完成，轮询等待剪贴板真正更新
        timeout = max(0.1, float(getattr(role_config, 'selection_copy_timeout', 0.8)))
        deadline = time.monotonic() + timeout
        selected_text = ""
        while time.monotonic() < deadline:
            time.sleep(0.05)
            clipboard_text = safe_paste()
            if clipboard_text and clipboard_text != clipboard_marker:
                selected_text = clipboard_text
                break

        # 没有复制到内容，或选中的是刚刚输出的内容
        if not selected_text or selected_text == state.last_output_text:
            return ""

        # 检查长度限制
        max_length = getattr(role_config, 'selection_max_length', 1000)
        if len(selected_text) > max_length:
            selected_text = selected_text[:max_length]

        # 如果开启了历史记录，检查选中文字是否与上一次使用的相同
        if role_config.enable_history:
            last_selection = _last_selection_by_role.get(role_name, "")
            if selected_text == last_selection:
                # 选中文字没有变化，且上一次已经使用过，不再加入上下文
                return ""

        # 检查是否只包含空白字符（空格、制表符、换行等）
        if not selected_text.strip():
            return ""

        return selected_text

    except Exception as e:
        logger.warning(f"获取选中文字失败: {e}")
        return ""
    finally:
        try:
            pyclip.copy(original_clipboard)
        except Exception as e:
            logger.warning(f"恢复剪贴板失败: {e}")


def get_clipboard_text(role_config, content: str) -> str:
    """语音内容命中关键词时，直接读取当前剪贴板文本。"""
    if not getattr(role_config, 'enable_read_clipboard', False):
        return ""

    # 默认角色不需要唤醒词，不能让普通听写意外读取剪贴板
    if role_config.display_name == role_config.DEFAULT_ROLE_NAME:
        return ""

    keywords = getattr(role_config, 'clipboard_keywords', ())
    if isinstance(keywords, str):
        keywords = (keywords,)

    matched_keyword = next(
        (word for word in keywords if word and word in (content or "")),
        None
    )
    if not matched_keyword:
        return ""

    clipboard_text = safe_paste().strip()
    if not clipboard_text:
        logger.info(f"检测到剪贴板关键词“{matched_keyword}”，但剪贴板中没有文本")
        return ""

    max_length = int(getattr(role_config, 'clipboard_max_length', 20000))
    if max_length > 0 and len(clipboard_text) > max_length:
        clipboard_text = clipboard_text[:max_length]

    logger.info(
        f"检测到剪贴板关键词“{matched_keyword}”，已读取剪贴板文本，长度: {len(clipboard_text)}"
    )
    return clipboard_text


def record_selection_usage(role_config, selection_text: str):
    """
    记录角色使用的选中文字（用于下一轮判断是否重复）

    Args:
        role_config: 角色配置 RoleConfig 对象
        selection_text: 使用的选中文字（空字符串表示没有使用）
    """
    global _last_selection_by_role
    role_name = role_config.name
    _last_selection_by_role[role_name] = selection_text
