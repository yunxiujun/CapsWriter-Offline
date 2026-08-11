"""
Toast 窗口基础模块

提供 Toast 窗口的抽象基类和通用工具函数。
"""
import logging
import tkinter as tk
from tkinter import font
from typing import Optional, Callable, Union
from abc import ABC, abstractmethod
import ctypes
import re

import markdown
from tkhtmlview import HTMLLabel

from .toast_constants import (
    DEFAULT_FONT_FAMILY,
    DEFAULT_PADDING_X,
    DEFAULT_PADDING_Y,
    MIN_WINDOW_HEIGHT,
    MARKDOWN_MIN_HEIGHT,
    SCROLL_STEP,
    DESTROY_DELAY_MS,
)
from . import logger

# DPI 感知设置（只调用一次，避免重复调用）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (OSError, AttributeError):
    # Windows 7 或不支持 DPI 感知的系统
    pass


# ============================================================
# 工具函数
# ============================================================

def add_zero_width_for_chinese(text: str) -> str:
    """在中文字符后添加零宽空格，强制 Label 按字符换行。
    
    这样可以避免中英混合时，Label 的单词边界换行导致不均匀。
    
    Args:
        text: 原始文本
        
    Returns:
        处理后的文本，每个中文字符后都添加了零宽空格
    """
    result = []
    for char in text:
        result.append(char)
        # 在中文字符（及全角字符）后插入零宽空格
        if ord(char) > 127:
            result.append('\u200B')  # 零宽空格
    return ''.join(result)


# ============================================================
# Toast 窗口抽象基类
# ============================================================

class ToastWindowBase(ABC):
    """Toast 窗口抽象基类
    
    提供窗口创建、拖动、鼠标事件处理、定时销毁等通用功能。
    子类需要实现 update_text 和 _destroy_content_widget 方法。
    
    Attributes:
        window: tkinter Toplevel 窗口对象
        streaming: 是否为流式输出模式
        markdown: 是否启用 Markdown 渲染
        full_text: 完整的文本内容
    """

    def __init__(
        self,
        parent_root: tk.Tk,
        text: str,
        font_size: int,
        font_family: str,
        bg: str,
        fg: str,
        duration: int,
        initial_width: Union[float, int],
        initial_height: int,
        position_y: int,
        fixed: bool,
        auto_dismiss: bool,
        streaming: bool,
        stop_callback: Optional[Callable[[], None]],
        markdown_enabled: bool,
        editable: bool = False,
        screen: int = 0,
        wrap_mode: str = 'word'
    ) -> None:
        """初始化 Toast 窗口基类
        
        Args:
            parent_root: 父窗口（Tk 主窗口）
            text: 初始文本内容
            font_size: 字体大小（像素）
            font_family: 字体名称，空字符串使用默认字体
            bg: 背景颜色
            fg: 前景色（文字颜色）
            duration: 自动关闭时长（毫秒）
            initial_width: 初始宽度，0-1 为屏幕比例，>1 为像素值
            initial_height: 初始高度，0 表示自动计算
            position_y: 窗口初始屏幕高度/y 坐标，-1 表示屏幕中间
            fixed: 是否固定在 position_y，固定后不可拖动改变位置
            auto_dismiss: 是否在 duration 后自动消失
            streaming: 是否为流式输出模式
            stop_callback: 窗口关闭时的回调函数
            markdown_enabled: 是否启用 Markdown 渲染
            editable: Markdown 渲染后是否允许编辑
        """
        # 保存基本属性
        self.parent_root = parent_root
        self.stop_callback = stop_callback
        self.streaming = streaming
        self.markdown = markdown_enabled
        self.editable = editable
        self.screen = screen
        self.wrap_mode = wrap_mode if wrap_mode in ('word', 'char') else 'word'
        self.duration = duration
        self.initial_width = initial_width
        self.initial_height = initial_height
        self.position_y = position_y
        self.fixed = fixed
        self.auto_dismiss = auto_dismiss
        self.fixed_callback: Optional[Callable[[bool], None]] = None
        self.auto_dismiss_callback: Optional[Callable[[bool], None]] = None
        self.position_callback: Optional[Callable[[int, int], None]] = None
        
        # 状态标志
        self.pause = False
        self.mouse_inside = False
        self.timer_id: Optional[str] = None
        
        # 拖动位置
        self.x = 0
        self.y = 0
        
        # 保存完整文本和样式配置（用于 Markdown 渲染）
        self.full_text = text
        self.font_size = font_size
        self.font_family = font_family if font_family else DEFAULT_FONT_FAMILY
        self.bg = bg
        self.fg = fg
        
        # 创建窗口
        self.window = tk.Toplevel(parent_root)
        self.window.hang_on = False
        
        # 设置窗口属性
        self.window.overrideredirect(True)  # 无边框模式
        self.window.attributes('-topmost', True)  # 保持置顶
        self.window.configure(bg=bg)
        self.window.resizable(True, True)
        self.window.pack_propagate(False)

        self.container = tk.Frame(self.window, bg=bg, borderwidth=0, highlightthickness=0)
        self.container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.content_frame = tk.Frame(self.container, bg=bg, borderwidth=0, highlightthickness=0)
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.controls_frame = tk.Frame(self.container, bg=bg, borderwidth=0, highlightthickness=0)
        self.controls_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self._create_control_buttons()
        
        # 绑定通用事件
        self._bind_common_events()
        
        # 显示窗口
        self.window.deiconify()
        
        if not self.streaming and self.auto_dismiss:
            self._start_destroy_timer()

    def _create_control_buttons(self) -> None:
        """创建右侧固定/取消固定控制按钮。"""
        button_options = {
            'width': 2,
            'height': 1,
            'font': (self.font_family, max(9, self.font_size - 3)),
            'fg': self.fg,
            'bg': self.bg,
            'activeforeground': self.fg,
            'activebackground': self.bg,
            'relief': tk.FLAT,
            'borderwidth': 0,
            'highlightthickness': 0,
            'cursor': 'hand2',
            'takefocus': False,
        }
        self.pin_button = tk.Button(
            self.controls_frame,
            text='固',
            command=self.pin_window,
            **button_options
        )
        self.pin_button.pack(side=tk.TOP, padx=(0, 4), pady=(4, 1))
        self.unpin_button = tk.Button(
            self.controls_frame,
            text='移',
            command=self.unpin_window,
            **button_options
        )
        self.unpin_button.pack(side=tk.TOP, padx=(0, 4), pady=(1, 4))
        self.dismiss_button = tk.Button(
            self.controls_frame,
            text='消',
            command=self.toggle_auto_dismiss,
            **button_options
        )
        self.dismiss_button.pack(side=tk.TOP, padx=(0, 4), pady=(1, 4))
        self._update_pin_button_state()
        self._update_dismiss_button_state()

    def _update_pin_button_state(self) -> None:
        """同步固定/移动按钮的互斥高亮状态。"""
        try:
            active_bg = self.fg
            active_fg = self.bg
            normal_bg = self.bg
            normal_fg = self.fg
            if self.fixed:
                self.pin_button.config(bg=active_bg, fg=active_fg, activebackground=active_bg, activeforeground=active_fg)
                self.unpin_button.config(bg=normal_bg, fg=normal_fg, activebackground=normal_bg, activeforeground=normal_fg)
            else:
                self.pin_button.config(bg=normal_bg, fg=normal_fg, activebackground=normal_bg, activeforeground=normal_fg)
                self.unpin_button.config(bg=active_bg, fg=active_fg, activebackground=active_bg, activeforeground=active_fg)
        except tk.TclError:
            pass

    def _update_dismiss_button_state(self) -> None:
        """同步自动消失按钮状态：消=会自动消失，留=不会自动消失。"""
        try:
            active_bg = self.fg
            active_fg = self.bg
            normal_bg = self.bg
            normal_fg = self.fg
            self.dismiss_button.config(text='消' if self.auto_dismiss else '留')
            self.dismiss_button.config(
                bg=active_bg,
                fg=active_fg,
                activebackground=active_bg,
                activeforeground=active_fg,
            )
            if self.auto_dismiss:
                self.dismiss_button.config(bg=normal_bg, fg=normal_fg, activebackground=normal_bg, activeforeground=normal_fg)
        except tk.TclError:
            pass

    def pin_window(self) -> None:
        """固定当前 Toast：锁住当前位置，不影响是否自动消失。"""
        try:
            self.window.update_idletasks()
            self.position_y = self.window.winfo_y()
            self.fixed = True
            if self.fixed_callback:
                self.fixed_callback(self.fixed)
            if self.position_callback:
                self.position_callback(self.window.winfo_x(), self.window.winfo_y())
            self.pause = False
            self._update_pin_button_state()
        except tk.TclError as e:
            logger.warning(f"固定 Toast 失败: {e}")

    def unpin_window(self) -> None:
        """取消固定：允许拖动，并恢复自动关闭计时。"""
        try:
            self.fixed = False
            if self.fixed_callback:
                self.fixed_callback(self.fixed)
            self._update_pin_button_state()
            if not self.streaming and not self.mouse_inside:
                self._start_destroy_timer()
        except tk.TclError as e:
            logger.warning(f"取消固定 Toast 失败: {e}")

    def toggle_auto_dismiss(self) -> None:
        """切换是否自动消失，并记住给后续 Toast 使用。"""
        try:
            self.auto_dismiss = not self.auto_dismiss
            if self.auto_dismiss_callback:
                self.auto_dismiss_callback(self.auto_dismiss)
            self._update_dismiss_button_state()
            if self.auto_dismiss:
                if not self.streaming and not self.mouse_inside:
                    self._start_destroy_timer()
            elif self.timer_id:
                self.window.after_cancel(self.timer_id)
                self.timer_id = None
        except tk.TclError as e:
            logger.warning(f"切换 Toast 自动消失状态失败: {e}")

    def _bind_common_events(self) -> None:
        """绑定通用事件（拖动、鼠标进入/离开、滚轮、ESC、复制）"""
        self.window.bind('<ButtonPress-1>', self._on_drag_start)
        self.window.bind('<ButtonRelease-1>', self._on_drag_stop)
        self.window.bind('<B1-Motion>', self._on_drag_motion)
        self.window.bind('<Escape>', self._destroy_window)
        self.window.bind('<Enter>', self._on_mouse_enter)
        self.window.bind('<Leave>', self._on_mouse_leave)
        self.window.bind('<MouseWheel>', self._on_mouse_wheel)
        self.window.bind('<Button-4>', self._on_mouse_wheel)  # Linux 向上滚动
        self.window.bind('<Button-5>', self._on_mouse_wheel)  # Linux 向下滚动
        self.window.bind('<Control-c>', self._on_copy)        # Ctrl+C 复制

    def _calculate_actual_width(self) -> int:
        """计算实际窗口宽度
        
        Returns:
            窗口宽度（像素）
        """
        screen_width = self.window.winfo_screenwidth()
        rect = self._monitor_rect(self.screen)
        if rect:
            screen_width = rect[2]
        if 0 < self.initial_width < 1:
            # 0-1 之间的小数，使用屏幕宽度的比例
            return int(screen_width * self.initial_width)
        else:
            # 绝对值（像素）
            return int(self.initial_width)

    def _calculate_position_y(self, screen_height: int, window_height: int) -> int:
        """计算 Toast 的屏幕 y 坐标。"""
        if self.position_y >= 0:
            max_y = max(screen_height - int(window_height), 0)
            return max(0, min(int(self.position_y), max_y))
        return screen_height // 2

    def _monitor_rect(self, screen: int = 0):
        """返回第 screen 块显示器的虚拟坐标矩形 (x, y, w, h)

        编号规则：0=主屏，1=第一块副屏，2=第二块副屏…（按枚举顺序）。
        screen <= 0 时使用主屏（返回 None 表示无需偏移）；失败时返回 None。
        """
        if screen <= 0:
            return None
        import ctypes
        from ctypes import wintypes
        try:
            monitors = []
            MONITORINFOF_PRIMARY = 0x00000001

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                ]

            @ctypes.WINFUNCTYPE(
                ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.POINTER(wintypes.RECT), ctypes.c_void_p
            )
            def _enum_cb(hmonitor, hdc, lprc, dwdata):
                r = lprc.contents
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                is_primary = False
                if ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
                    is_primary = bool(mi.dwFlags & MONITORINFOF_PRIMARY)
                monitors.append(((r.left, r.top, r.right - r.left, r.bottom - r.top), is_primary))
                return 1

            ctypes.windll.user32.EnumDisplayMonitors(None, None, _enum_cb, None)
            ordered = [m for m in monitors if m[1]] + [m for m in monitors if not m[1]]
            if 0 < screen < len(ordered):
                return ordered[screen][0]
        except Exception:
            pass
        return None

    def _available_window_height(
        self, screen_height: int, origin_y: int = 0, initial: bool = False
    ) -> int:
        """计算窗口从当前位置到屏幕底部可使用的最大高度。"""
        if initial:
            relative_y = self.position_y if self.position_y >= 0 else screen_height // 2
        else:
            try:
                relative_y = max(0, self.window.winfo_y() - origin_y)
            except tk.TclError:
                relative_y = 0
        return max(MIN_WINDOW_HEIGHT, screen_height - int(relative_y) - 8)

    @staticmethod
    def _invert_color(hex_color: str) -> str:
        """计算十六进制颜色的反色
        
        Args:
            hex_color: 十六进制颜色值（如 '#075077'）
            
        Returns:
            反色的十六进制颜色值
        """
        # 去掉 # 前缀
        hex_color = hex_color.lstrip('#')
        # 解析 RGB 值
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        # 计算反色
        inv_r = 255 - r
        inv_g = 255 - g
        inv_b = 255 - b
        return f"#{inv_r:02x}{inv_g:02x}{inv_b:02x}"

    # --------------------------------------------------------
    # 鼠标事件处理
    # --------------------------------------------------------

    def _on_mouse_enter(self, event: tk.Event) -> None:
        """鼠标进入窗口，暂停自动关闭计时器"""
        self.mouse_inside = True
        if self.timer_id:
            self.window.after_cancel(self.timer_id)
            self.timer_id = None

    def _on_mouse_leave(self, event: tk.Event) -> None:
        """鼠标离开窗口，恢复自动关闭计时器"""
        self.mouse_inside = False
        if not self.streaming and self.auto_dismiss:
            self._start_destroy_timer()

    def _on_drag_start(self, event: tk.Event) -> None:
        """拖动开始"""
        if self.fixed:
            return
        self.pause = True
        self.x = event.x
        self.y = event.y

    def _on_drag_stop(self, event: tk.Event) -> None:
        """拖动结束"""
        if self.fixed:
            return
        self.pause = False
        if self.position_callback:
            self.position_callback(self.window.winfo_x(), self.window.winfo_y())

    def _on_drag_motion(self, event: tk.Event) -> None:
        """拖动中，更新窗口位置"""
        if self.fixed:
            return
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.window.winfo_x() + deltax
        y = self.window.winfo_y() + deltay
        self.window.geometry(f"+{x}+{y}")

    def _on_mouse_wheel(self, event: tk.Event) -> str:
        """滚轮只滚动 Toast 内容，不改变窗口位置。"""
        return self._scroll_content(event)

    def _scroll_content(self, event: tk.Event) -> str:
        """滚动当前内容控件，避免滚轮把整个窗口拖动。"""
        try:
            widget = getattr(self, 'md_label', None) or getattr(self, 'text_area', None)
            if widget is None or not hasattr(widget, 'yview_scroll'):
                return "break"

            delta = getattr(event, 'delta', 0)
            num = getattr(event, 'num', 0)
            if delta:
                amount = -1 if delta > 0 else 1
            elif num:
                amount = -1 if num == 4 else 1
            else:
                return "break"

            widget.yview_scroll(amount, 'units')
            return "break"
        except tk.TclError as e:
            logger.debug(f"Toast 内容滚动失败: {e}")
            return "break"

    def _on_copy(self, _event: tk.Event) -> str:
        """复制文本到剪贴板
        
        优先复制选中的文本（如果有），否则复制全部内容。

        Args:
            _event: 事件对象（未使用）

        Returns:
            "break" 阻止事件继续传播
        """
        try:
            text_to_copy = None
            
            # 如果有 md_label，检查是否有选中文本
            if hasattr(self, 'md_label') and self.md_label:
                try:
                    # Text 组件使用 tag_ranges("sel") 检查选区
                    sel_ranges = self.md_label.tag_ranges("sel")
                    if sel_ranges:
                        # 有选中文本，获取选中内容
                        text_to_copy = self.md_label.get(sel_ranges[0], sel_ranges[1])
                        logger.info("已复制选中的文本到剪贴板")
                except tk.TclError:
                    pass  # 没有选区或其他错误
            
            # 如果没有选中文本，复制全部内容
            if text_to_copy is None:
                text_to_copy = self.full_text
                logger.info("已复制 Toast 全部内容到剪贴板")
            
            self.window.clipboard_clear()
            self.window.clipboard_append(text_to_copy)
        except Exception as e:
            logger.error(f"复制到剪贴板失败: {e}")
        return "break"

    # --------------------------------------------------------
    # 窗口销毁
    # --------------------------------------------------------

    def _start_destroy_timer(self) -> None:
        """启动自动销毁计时器"""
        if not self.auto_dismiss:
            if self.timer_id:
                self.window.after_cancel(self.timer_id)
                self.timer_id = None
            return
        if self.timer_id:
            self.window.after_cancel(self.timer_id)
        self.timer_id = self.window.after(self.duration, self._destroy_window)

    def _destroy_window(self, event: Optional[tk.Event] = None) -> None:
        """销毁窗口
        
        Args:
            event: 事件对象（ESC 键触发时传入）
        """
        try:
            if not self.auto_dismiss and event is None:
                return

            # 调用停止回调（用于停止 LLM 输出）
            if self.stop_callback:
                try:
                    self.stop_callback()
                except Exception as e:
                    logger.warning(f"停止回调执行失败: {e}")

            if self.pause:
                # 如果窗口被暂停（拖动），延迟销毁
                if self.timer_id:
                    self.window.after_cancel(self.timer_id)
                self.timer_id = self.window.after(DESTROY_DELAY_MS, self._destroy_window)
            else:
                if self.timer_id:
                    self.window.after_cancel(self.timer_id)
                    self.timer_id = None
                self.window.destroy()
        except tk.TclError:
            # 窗口可能已被销毁
            pass

    # --------------------------------------------------------
    # Markdown 渲染
    # --------------------------------------------------------

    def _calculate_height_coefficient(self, content_height: int) -> float:
        """根据内容高度计算边距系数

        使用指数衰减曲线：f(x) = 0.5 * e^(-0.003x) + 1.1
        当内容高度较小时，需要更大的边距系数以确保内容完全显示。
        当内容高度较大时，系数逐渐接近极限值 1.1。

        Args:
            content_height: 内容高度（像素）

        Returns:
            边距系数，范围 (1.1, 1.6]
            - x=50: f(50) ≈ 1.6
            - x=300: f(300) ≈ 1.3
            - x=1500: f(1500) ≈ 1.15
            - x→∞: f(x) → 1.1
        """
        import math

        if content_height <= 50:
            return 1.6

        # 指数衰减曲线：f(x) = 0.5 * e^(-0.003x) + 1.1
        coefficient = 0.5 * math.exp(-0.003 * content_height) + 1.1

        # 确保系数在合理范围内
        return max(coefficient, 1.1)

    @staticmethod
    def _normalize_markdown_layout(text: str) -> str:
        """合并孤立的 Markdown 列表/标题标记，避免渲染器拆成空行。"""
        lines = text.splitlines()
        normalized = []
        index = 0
        marker_pattern = re.compile(r'^\s*(?:[-+*]|\d+[.)]|#{1,6})\s*$')
        while index < len(lines):
            current = lines[index]
            if marker_pattern.fullmatch(current):
                next_index = index + 1
                while next_index < len(lines) and not lines[next_index].strip():
                    next_index += 1
                if next_index < len(lines):
                    normalized.append(
                        f"{current.rstrip()} {lines[next_index].lstrip()}"
                    )
                    index = next_index + 1
                    continue
            normalized.append(current)
            index += 1
        return re.sub(r'\n{3,}', '\n\n', '\n'.join(normalized))

    def _switch_to_markdown(self) -> None:
        """将内容组件切换为 Markdown 渲染"""
        try:
            # 保存当前位置
            cx, cy = self.window.winfo_x(), self.window.winfo_y()

            # 转换 Markdown 为 HTML
            raw_html = markdown.markdown(
                self._normalize_markdown_layout(self.full_text),
                extensions=['extra', 'nl2br']
            )

            # 包装为完整的 HTML（不设置 padding，让 HTMLLabel 组件处理）
            full_html = f"""
            <div style="background-color:{self.bg}; color:{self.fg};
                        font-family:{self.font_family}; font-size:{self.font_size}px;">
                {raw_html}
            </div>
            """

            # 先创建 HTMLLabel 组件，覆盖在原有组件上面
            self.md_label = HTMLLabel(
                self.content_frame,
                html=full_html,
                wrap=self.wrap_mode,
                background=self.bg,
                padx=DEFAULT_PADDING_X,
                pady=DEFAULT_PADDING_Y
            )
            self.md_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                self.md_label.bind(sequence, self._scroll_content)
            
            # 根据 editable 参数设置是否可编辑
            # DISABLED 状态下仍可选择文字，但无法编辑
            # NORMAL 状态下可以选择和编辑文字
            if self.editable:
                self.md_label.config(state=tk.NORMAL)
                
                # 设置光标颜色为背景色的反色
                cursor_color = self._invert_color(self.bg)
                self.md_label.config(insertbackground=cursor_color, insertwidth=2)
            # 否则保持 HTMLLabel 默认的 DISABLED 状态
            
            # 设置选中文字的高亮样式（DISABLED 状态下默认选中样式不可见）
            select_bg = "#3399ff"
            select_fg = "white"
            self.md_label.config(selectbackground=select_bg, selectforeground=select_fg)
            
            # HTMLLabel 使用 tag 设置文字样式，需要为所有 tag 也设置选中样式
            for tag in self.md_label.tag_names():
                self.md_label.tag_config(tag, selectbackground=select_bg, selectforeground=select_fg)

            # 现在 Markdown 组件已经显示，再销毁原有组件
            self._destroy_content_widget()

            # 多次更新以确保布局完全计算
            self.window.update()
            self.window.update_idletasks()

            # 使用 fit_height() 方法获取真实的内容高度
            # 这会自动调整标签高度以适应所有内容
            self.md_label.fit_height()
            self.window.update()
            self.window.update_idletasks()

            # 测量 fit_height() 后的高度
            height_after = self.md_label.winfo_height()
            reqheight_after = self.md_label.winfo_reqheight()

            # 使用较大的高度值（reqheight 可能更准确）
            content_height = max(height_after, reqheight_after)

            # 计算新的窗口高度和宽度
            # 使用动态系数确保内容完全显示
            margin_coefficient = self._calculate_height_coefficient(content_height)
            final_h = max(int(content_height * margin_coefficient), MARKDOWN_MIN_HEIGHT)
            monitor_rect = self._monitor_rect(self.screen)
            if monitor_rect:
                monitor_y, monitor_height = monitor_rect[1], monitor_rect[3]
            else:
                monitor_y, monitor_height = 0, self.window.winfo_screenheight()
            final_h = min(
                final_h,
                self._available_window_height(monitor_height, monitor_y),
            )
            try:
                line_height = max(int(self.font_size * 1.5), 1)
                visible_lines = max(
                    1,
                    int((final_h - DEFAULT_PADDING_Y * 2) / line_height),
                )
                self.md_label.config(height=visible_lines)
            except tk.TclError:
                pass
            final_w = self._calculate_actual_width()
            if self.fixed and not getattr(self, '_group_id', None):
                cy = monitor_y + self._calculate_position_y(monitor_height, final_h)

            self.window.geometry(f"{final_w}x{int(final_h)}+{cx}+{cy}")

            # 更新布局后再次测量
            self.window.update()
            self.window.update_idletasks()

            logger.info(f"Markdown 窗口: {final_w}x{final_h} (内容: {content_height}px, 系数: {margin_coefficient:.2f})")

        except Exception as e:
            logger.error(f"Markdown 转换失败: {e}")
            self._destroy_window()

    # --------------------------------------------------------
    # 抽象方法（子类必须实现）
    # --------------------------------------------------------

    @abstractmethod
    def update_text(self, new_text: str) -> None:
        """更新文本内容（由子类实现）
        
        Args:
            new_text: 新的完整文本内容
        """
        pass

    @abstractmethod
    def _destroy_content_widget(self) -> None:
        """销毁内容组件（由子类实现）"""
        pass

    # --------------------------------------------------------
    # 流式输出完成
    # --------------------------------------------------------

    def finish(self, start_timer: bool = True) -> None:
        """完成流式输出

        标记流式输出结束，如果启用了 Markdown 则转换渲染，
        然后启动自动销毁计时器。
        """
        if self.streaming:
            self.streaming = False

            # 如果启用了 Markdown，转换渲染
            if self.markdown:
                self._switch_to_markdown()

            # 只有当鼠标不在窗口内时才启动计时器
            if start_timer and not self.mouse_inside and self.auto_dismiss:
                self._start_destroy_timer()
