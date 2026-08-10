from __future__ import annotations
"""
Toast 消息管理器模块

提供 ToastMessageManager 单例类，管理所有 Toast 窗口的生命周期。
"""
import logging
import threading
import tkinter as tk
import json
from queue import Queue
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Callable, Union, List, TYPE_CHECKING
import sys
import os

# 直接运行时，将项目根目录添加到 sys.path
if __name__ == "__main__":
    file_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(file_dir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from core.ui.toast_text import ToastWindowText
    from core.ui.toast_label import ToastWindowLabel
    from core.ui.toast_constants import (
        QUEUE_POLL_INTERVAL_MS,
        DEFAULT_DURATION_MS,
        DEFAULT_INITIAL_WIDTH,
        TK_SCALING_FACTOR,
    )
    from core.ui.toast_logger import get_toast_logger
else:
    from .toast_text import ToastWindowText
    from .toast_label import ToastWindowLabel
    from .toast_constants import (
        QUEUE_POLL_INTERVAL_MS,
        DEFAULT_DURATION_MS,
        DEFAULT_INITIAL_WIDTH,
        TK_SCALING_FACTOR,
    )
    from .toast_logger import get_toast_logger

# 用于类型注解的前向引用
if TYPE_CHECKING:
    from .toast_base import ToastWindowBase


# 配置日志（智能检测主程序配置）
logger = get_toast_logger(__name__)


# ============================================================
# 数据类
# ============================================================

@dataclass
class ToastMessage:
    """Toast 消息配置数据类

    Attributes:
        text: 消息文本内容
        font_size: 字体大小（像素）
        font_family: 字体名称，空字符串使用系统默认
        bg: 背景颜色（十六进制或颜色名）
        fg: 前景色（文字颜色）
        duration: 显示时长（毫秒）
        initial_width: 初始宽度，0-1 为屏幕比例，>1 为像素值
        initial_height: 初始高度，0 表示自动计算
        position_y: 窗口初始屏幕高度/y 坐标，-1 表示屏幕中间
        fixed: 是否固定在 position_y，固定后不可拖动改变位置
        auto_dismiss: 是否在 duration 后自动消失
        streaming: 是否为流式模式
        window_type: 窗口类型 ('text' 或 'label')
        stop_callback: 窗口关闭时的回调函数
        markdown: 是否启用 Markdown 渲染
    """
    text: str
    font_size: int = 14
    font_family: str = ''
    bg: str = '#075077'
    fg: str = 'white'
    duration: int = DEFAULT_DURATION_MS
    initial_width: Union[float, int] = DEFAULT_INITIAL_WIDTH
    initial_height: int = 0
    position_y: int = -1
    fixed: bool = False
    auto_dismiss: bool = True
    streaming: bool = False
    window_type: Literal['text', 'label'] = 'text'
    stop_callback: Optional[Callable[[], None]] = None
    markdown: bool = False
    editable: bool = False  # Markdown 渲染后是否允许编辑
    screen: int = 0          # 0=主屏，1=第一块副屏（Windows 多显示器）
    wrap_mode: str = 'word'   # Markdown 换行模式
    group_id: Optional[str] = None
    group_index: int = 0
    group_size: int = 1
    group_gap: int = 0
    fixed_callback: Optional[Callable[[bool], None]] = None
    auto_dismiss_callback: Optional[Callable[[bool], None]] = None


# ============================================================
# Toast 消息管理器
# ============================================================

class ToastMessageManager:
    """Toast 消息管理器（单例模式）

    在独立的线程中运行 Tkinter 主循环，管理所有 Toast 窗口的生命周期。

    Features:
        - 单例模式，确保只有一个 Tkinter 主循环
        - 消息队列，支持并发添加消息
        - 活动窗口跟踪，支持流式输出更新
        - UUID 消息标识，精确匹配和操作
    """

    _instance: Optional[ToastMessageManager] = None
    _lock = threading.Lock()

    def __new__(cls) -> ToastMessageManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        self.message_queue: Queue[ToastMessage] = Queue()
        self.is_running = False
        self.active_windows: List = []  # 运行时类型，避免循环导入
        self.root: Optional[tk.Tk] = None
        self.parallel_groups = {}
        self.parallel_group_lock = threading.Lock()
        self.state_path = Path(__file__).resolve().parents[2] / '.toast_state.json'
        self.fixed_preference: Optional[bool] = None
        self.auto_dismiss_preference: Optional[bool] = None
        self._load_state()

        # 在子线程中启动 Tkinter
        self.manager_thread = threading.Thread(
            target=self._run_manager,
            daemon=True,
            name="ToastManagerThread"
        )
        self.manager_thread.start()

    def _run_manager(self) -> None:
        """在子线程中运行 Tkinter 主循环"""
        # 创建隐藏的主窗口
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.tk.call('tk', 'scaling', TK_SCALING_FACTOR)

        # 设置窗口关闭时的行为
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 开始处理队列
        self.is_running = True
        self._process_queue()

        # 启动 Tkinter 主循环
        self.root.mainloop()

    def _on_close(self) -> None:
        """关闭所有窗口并退出"""
        self.is_running = False

        for window in self.active_windows[:]:
            try:
                window.window.destroy()
            except tk.TclError:
                pass

        self.active_windows.clear()

        if self.root:
            self.root.quit()

    def _process_queue(self) -> None:
        """处理队列中的消息"""
        try:
            if not self.message_queue.empty():
                msg = self.message_queue.get_nowait()
                msg_id = getattr(msg, '_id', 'unknown')

                # 根据 window_type 选择窗口类
                WindowClass = ToastWindowLabel if msg.window_type == 'label' else ToastWindowText
                if self.fixed_preference is not None:
                    msg.fixed = self.fixed_preference
                if self.auto_dismiss_preference is not None:
                    msg.auto_dismiss = self.auto_dismiss_preference
                msg.fixed_callback = self._set_fixed_preference
                msg.auto_dismiss_callback = self._set_auto_dismiss_preference

                toast_window = WindowClass(
                    self.root,
                    msg.text,
                    msg.font_size,
                    msg.font_family,
                    msg.bg,
                    msg.fg,
                    msg.duration,
                    msg.initial_width,
                    msg.initial_height,
                    msg.position_y,
                    msg.fixed,
                    msg.auto_dismiss,
                    streaming=msg.streaming,
                    stop_callback=msg.stop_callback,
                    markdown=msg.markdown,
                    editable=msg.editable,
                    screen=msg.screen,
                    wrap_mode=msg.wrap_mode
                )
                toast_window._group_id = msg.group_id
                toast_window._group_index = msg.group_index
                toast_window._group_size = msg.group_size
                toast_window._group_gap = msg.group_gap
                toast_window.fixed_callback = msg.fixed_callback
                toast_window.auto_dismiss_callback = msg.auto_dismiss_callback

                # 保存消息ID到窗口对象
                toast_window._msg_id = msg_id
                self.active_windows.append(toast_window)

                # 设置窗口销毁时的回调
                toast_window.window.bind(
                    '<Destroy>',
                    lambda _, w=toast_window: self._remove_window(w)
                )
                if msg.group_id:
                    self._layout_group(msg.group_id, msg.screen)

            # 清理已销毁的窗口
            self.active_windows = [
                w for w in self.active_windows
                if self._window_exists(w)
            ]

        except Exception as e:
            logger.warning(f"处理队列消息时出错: {e}")

        # 继续处理队列
        if self.is_running and self.root:
            self.root.after(QUEUE_POLL_INTERVAL_MS, self._process_queue)

    def _window_exists(self, window) -> bool:
        """检查窗口是否存在"""
        try:
            return window.window.winfo_exists()
        except tk.TclError:
            return False

    def _remove_window(self, window) -> None:
        """从活动窗口列表中移除窗口"""
        if window in self.active_windows:
            self.active_windows.remove(window)

    def _set_auto_dismiss_preference(self, auto_dismiss: bool) -> None:
        """记住用户最近一次选择的 Toast 自动消失状态。"""
        self.auto_dismiss_preference = auto_dismiss
        self._save_state()

    def _set_fixed_preference(self, fixed: bool) -> None:
        """记住用户最近一次选择的 Toast 固定/移动状态。"""
        self.fixed_preference = fixed
        self._save_state()

    def _load_state(self) -> None:
        """读取 Toast 持久化状态。"""
        try:
            if not self.state_path.exists():
                return
            data = json.loads(self.state_path.read_text(encoding='utf-8'))
            fixed = data.get('fixed')
            auto_dismiss = data.get('auto_dismiss')
            if isinstance(fixed, bool):
                self.fixed_preference = fixed
            if isinstance(auto_dismiss, bool):
                self.auto_dismiss_preference = auto_dismiss
        except Exception as e:
            logger.warning(f"读取 Toast 状态失败: {e}")

    def _save_state(self) -> None:
        """保存 Toast 持久化状态。"""
        try:
            data = {
                'fixed': self.fixed_preference,
                'auto_dismiss': self.auto_dismiss_preference,
            }
            self.state_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.warning(f"保存 Toast 状态失败: {e}")

    def _register_group_message(self, msg_id: str, msg: ToastMessage) -> None:
        """登记并行 Toast，供同屏布局和统一倒计时使用。"""
        if not msg.group_id:
            return
        with self.parallel_group_lock:
            group = self.parallel_groups.setdefault(
                msg.group_id,
                {
                    'expected': msg.group_size,
                    'members': {},
                    'done': set(),
                    'scheduled': False,
                    'duration': 0,
                },
            )
            group['expected'] = max(group['expected'], msg.group_size)
            group['members'][msg_id] = {
                'screen': msg.screen,
                'index': msg.group_index,
                'duration': msg.duration,
            }
            group['duration'] = max(group['duration'], msg.duration)

    def _screen_rect(self, window, screen: int):
        """获取 Toast 目标屏幕的虚拟桌面矩形。"""
        if screen > 0:
            rect = window._monitor_rect(screen)
            if rect:
                return rect
        return (
            0,
            0,
            window.window.winfo_screenwidth(),
            window.window.winfo_screenheight(),
        )

    def _layout_group(self, group_id: str, screen: int, equalize_height: bool = False) -> None:
        """将同屏并行 Toast 横向贴合排列。"""
        windows = [
            window
            for window in self.active_windows
            if getattr(window, '_group_id', None) == group_id
            and getattr(window, 'screen', 0) == screen
            and self._window_exists(window)
        ]
        if not windows:
            return
        if len(windows) == 1:
            # 单窗口保持原有宽度和拖动行为。
            return

        windows.sort(key=lambda window: getattr(window, '_group_index', 0))
        reference = windows[0]
        origin_x, origin_y, screen_width, screen_height = self._screen_rect(reference, screen)
        gap = max(0, int(getattr(reference, '_group_gap', 8)))
        tile_width = max(240, (screen_width - gap * (len(windows) - 1)) // len(windows))

        for window in windows:
            try:
                window.initial_width = tile_width
                window._set_window_position(initial=False)
            except tk.TclError:
                pass

        target_height = max(window.window.winfo_height() for window in windows) if equalize_height else None
        base_y = min(window.window.winfo_y() for window in windows)
        for index, window in enumerate(windows):
            try:
                x = origin_x + index * (tile_width + gap)
                height = target_height or window.window.winfo_height()
                window.window.geometry(
                    f"{tile_width}x{height}+{x}+{base_y}"
                )
            except tk.TclError:
                pass

    def _mark_group_done(self, group_id: str, msg_id: str) -> None:
        """记录一个并行成员完成；最后一个完成时统一启动倒计时。"""
        if not group_id:
            return
        with self.parallel_group_lock:
            group = self.parallel_groups.get(group_id)
            if not group:
                return
            group['done'].add(msg_id)
            if group['scheduled'] or len(group['done']) < group['expected']:
                return
            windows = [
                window for window in self.active_windows
                if getattr(window, '_group_id', None) == group_id
            ]
            if not windows:
                return
            duration = max(group['duration'], 0)
            auto_dismiss = all(window.auto_dismiss for window in windows)
            if auto_dismiss:
                group['scheduled'] = True

        screens = {getattr(window, 'screen', 0) for window in windows}
        for screen in screens:
            self._layout_group(group_id, screen, equalize_height=True)

        if not auto_dismiss:
            return
        # 成员已经各自完成 Markdown 渲染，现在统一从最后一个完成时刻计时。
        for window in windows:
            try:
                window.duration = duration
                if not window.mouse_inside:
                    window._start_destroy_timer()
            except tk.TclError:
                pass

    def add_message(self, msg: ToastMessage) -> Optional[str]:
        """添加 ToastMessage 对象到队列

        Args:
            msg: Toast 消息配置对象

        Returns:
            消息唯一标识符（用于后续更新、完成、关闭操作）
        """
        import uuid
        msg_id = str(uuid.uuid4())
        msg._id = msg_id  # 添加唯一标识符
        self._register_group_message(msg_id, msg)
        self.message_queue.put(msg)
        return msg_id

    def update_toast(self, msg_id: str, new_text: str) -> None:
        """更新指定 ID 的 Toast 文字

        Args:
            msg_id: 消息唯一标识符
            new_text: 新的完整文本内容
        """
        for window in self.active_windows:
            if getattr(window, '_msg_id', None) == msg_id:
                window.update_text(new_text)
                return
        logger.warning(f"未找到消息 ID: {msg_id[:8]}")

    def finish_toast(self, msg_id: str) -> None:
        """完成指定 ID 的 Toast 的流式输出

        Args:
            msg_id: 消息唯一标识符
        """
        for window in self.active_windows:
            if getattr(window, '_msg_id', None) == msg_id:
                if window.streaming:
                    group_id = getattr(window, '_group_id', None)
                    window.finish(start_timer=not group_id)
                    if group_id:
                        self._mark_group_done(group_id, msg_id)
                return
        logger.warning(f"未找到消息 ID: {msg_id[:8]}")

    def close_toast(self, msg_id: str) -> None:
        """关闭指定 ID 的 Toast

        Args:
            msg_id: 消息唯一标识符
        """
        for window in self.active_windows[:]:
            if getattr(window, '_msg_id', None) == msg_id:
                group_id = getattr(window, '_group_id', None)
                if group_id:
                    self._mark_group_done(group_id, msg_id)
                try:
                    window.window.destroy()
                    self.active_windows.remove(window)
                except (tk.TclError, ValueError):
                    pass
                return
        logger.warning(f"未找到消息 ID: {msg_id[:8]}")

    async def wait_for_window(self, msg_id: str, timeout: float = 1.0) -> Optional[ToastWindowBase]:
        """异步等待指定 ID 的窗口创建完成

        Args:
            msg_id: 消息唯一标识符
            timeout: 超时时间（秒）

        Returns:
            窗口对象，如果超时则返回 None
        """
        import asyncio
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            for window in self.active_windows:
                if getattr(window, '_msg_id', None) == msg_id:
                    return window
            await asyncio.sleep(0.01)  # 10ms 轮询间隔
        logger.warning(f"等待窗口超时: {msg_id[:8]}")
        return None
