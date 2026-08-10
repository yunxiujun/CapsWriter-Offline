"""
LLM 角色配置 Dataclass

使用 Dataclass 替代字典，提供类型安全和更好的 IDE 支持
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple


@dataclass
class RoleConfig:
    """角色配置

    包含单个角色的所有配置信息
    """
    # 静态常量
    DEFAULT_ROLE_NAME = '默认'

    # 基本信息
    name: str = ''                               # 角色显示名称
    module_name: str = ""                         # 模块名称（如 "LLM.翻译"）
    enabled: bool = True                          # 是否启用此角色

    # API 配置
    provider: str = 'ollama'                      # API 提供商
    api_url: str = ''                             # API 地址
    api_key: str = ''                             # API Key
    model: str = 'gemma3:4b'                      # 模型名称

    # 上下文管理
    max_context_length: int = 4096                # 最大上下文长度（token 数）

    # 功能配置
    enable_thinking: bool = False                 # 是否启用思考（仅 Ollama 支持）
    parallel_roles: Tuple[str, ...] = ()          # 触发本角色时并行调用的其他角色名（各自显示 Toast，禁止嵌套）
    parallel_gap: int = 0                          # 同屏并行 Toast 之间的间距（像素）
    enable_history: bool = False                  # 是否保留对话历史
    enable_hotwords: bool = False                 # 是否读取潜在热词列表
    enable_read_selection: bool = False           # 是否读取鼠标所选文字（通过 Ctrl+C）
    selection_max_length: int = 20000             # 选中文字最大长度
    selection_copy_timeout: float = 0.8           # 等待 Ctrl+C 完成的最长时间（秒）
    enable_read_clipboard: bool = True             # 语音命中关键词时直接读取剪贴板
    clipboard_keywords: Tuple[str, ...] = (        # 剪贴板触发关键词（兼容常见识别结果）
        '剪贴板', '剪切板', '剪贴版', '剪切版'
    )
    clipboard_max_length: int = 20000             # 剪贴板内容最大长度
    enable_knowledge_base: bool = False           # 是否启用角色同名本地知识库
    knowledge_base_folder: str = ''               # 空值使用 LLM知识库/<角色主名称>
    knowledge_base_top_k: int = 8                 # 大型知识库最多检索的相关片段数
    knowledge_base_max_chars: int = 50000         # 单次请求最多注入的知识库字符数
    knowledge_base_evidence_max_chars: int = 12000  # 回答后最多附加的相关原文字符数
    knowledge_base_evidence_top_k: int = 2        # 回答后最多附加的相关原文段落数
    knowledge_base_evidence_score_ratio: float = 0.80  # 附加段落相对最高分的最低比例
    knowledge_base_chunk_chars: int = 1600        # 单个检索片段的目标字符数
    knowledge_base_max_file_bytes: int = 2097152  # 单个知识文件最大 2 MiB

    # 输出配置
    output_mode: str = 'typing'                   # 输出方式: 'typing' 或 'toast' (即打字输出或弹窗输出)

    # Toast 弹窗配置
    toast_initial_width: float = 0.5              # Toast 窗口初始宽度（0.5 = 50% 屏幕宽度）
    toast_initial_height: int = 0                 # Toast 窗口初始高度（0 表示自动计算）
    toast_position_y: int = -1                    # Toast 窗口初始屏幕高度/y 坐标（-1 表示屏幕中间）
    toast_font_family: str = ''                   # Toast 字体（空字符串表示使用系统默认）
    toast_font_size: int = 14                     # Toast 字体大小
    toast_font_color: str = 'white'               # Toast 字体颜色
    toast_bg_color: str = '#075077'               # Toast 背景颜色
    toast_duration: int = 3000                    # Toast 显示时长（毫秒）
    toast_editable: bool = False                  # Toast 是否可编辑（Markdown 渲染后）
    toast_screen: int = 0                         # 0=主屏，1=第一块副屏（Windows 多显示器）
    toast_title: str = ''                         # Toast 顶部标题（如模型名），留空不显示
    toast_wrap_mode: str = 'word'                  # Markdown 换行：word 更少拆分，char 适合逐字符换行

    # 生成参数
    temperature: float = 0.7                      # 温度（0-2）
    top_p: float = 0.9                            # Top-p 采样
    max_tokens: int = 1024                        # 最大输出 token 数（0 表示使用模型默认值）
    stop: str = ''                                # 停止序列

    # 高级选项
    extra_options: Dict[str, Any] = field(default_factory=dict)  # 额外的 API 参数

    # 提示词前缀
    prompt_prefix_hotwords: str = '热词列表：'      # 热词列表前缀
    prompt_prefix_selection: str = '选中文字：'     # 选中文字前缀
    prompt_prefix_clipboard: str = '剪贴板内容：'    # 剪贴板内容前缀
    prompt_prefix_knowledge_base: str = '本地知识库资料：'  # 知识库资料前缀
    prompt_prefix_input: str = '用户输入：'         # 用户输入前缀

    # System Prompt
    system_prompt: str = ''                       # 系统提示词

    @property
    def display_name(self) -> str:
        """显示名称：name 按 | 分割的第一部分"""
        parts = [p.strip() for p in self.name.split('|')] if self.name else ['']
        return parts[0]

    @property
    def names(self) -> list:
        """所有名称列表：name 按 | 分割的所有非空部分"""
        parts = [p.strip() for p in self.name.split('|')] if self.name else ['']
        return [p for p in parts if p]
