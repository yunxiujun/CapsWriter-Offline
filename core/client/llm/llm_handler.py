"""
LLM 处理器 - 协调器

功能：
1. 协调各个组件（角色加载、上下文管理、客户端池、消息构建）
2. 提供统一的处理接口
3. 流式输出
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Optional, Any
from pathlib import Path
import asyncio
import re
import uuid

from .llm_role_loader import RoleLoader
from .llm_context import ContextManager
from .llm_watcher import LLMFileWatcher
from .llm_role_config import RoleConfig
from .llm_client_pool import ClientPool
from .llm_message_builder import MessageBuilder
from .llm_role_detector import RoleDetector
from .llm_processor import LLMProcessor
from .llm_knowledge_base import KnowledgeBaseRetriever, format_evidence_appendix
from .llm_get_selection import (
    get_selected_text,
    get_clipboard_text,
    record_selection_usage,
)
from . import logger
from .llm_stop_monitor import StopMonitor
from core.client.udp.udp_broadcaster import broadcast_output_udp


@dataclass
class LLMResult:
    """LLM 处理结果"""
    result: str                    # 润色后的文本
    role_name: Optional[str]       # 角色名
    processed: bool                # 是否经过处理
    token_count: int               # token数
    polish_time: float             # 总耗时（秒）
    input_text: str                # 输入文本（已移除角色前缀）
    generation_time: float = 0.0   # 生成时间（秒，从第一个 token 开始）


# ======================================================================
# --- LLM 处理器（协调器）---

class LLMHandler:
    """LLM 润色处理器（协调器）"""

    def __init__(self, app):
        logger.info("初始化 LLM 处理器")
        self.app = app

        # 获取热词管理器
        self.hotword_manager = app.hotword

        # 角色管理
        self.role_loader = RoleLoader()
        self.roles = self.role_loader.get_roles()
        logger.info(f"已加载角色: {list(self.roles.keys())}")

        # 上下文管理器池
        self.context_managers: Dict[str, ContextManager] = {}
        self._init_context_managers()

        # 客户端池
        self.client_pool = ClientPool()

        # 消息构建器
        self.message_builder = MessageBuilder(app)
        self.knowledge_base = KnowledgeBaseRetriever()

        # 角色检测器
        self.role_detector = RoleDetector(self.role_loader)

        # LLM 处理引擎
        self.processor = LLMProcessor(self.client_pool)

        # 5. 子服务监控
        # 配置文件监控
        self.watcher = LLMFileWatcher(
            on_roles_reload=lambda: self.reload_roles(),
            get_roles=lambda: self.roles,
        )
        # 中断按键监控
        self.monitor = StopMonitor()

    def start(self):
        """启动 LLM 系统的子服务监控"""
        self.watcher.start()
        self.monitor.start()
        logger.debug("LLM 系统子服务已启动")

    def stop(self):
        """停止 LLM 系统的子服务监控"""
        self.watcher.stop()
        self.monitor.stop()
        logger.debug("LLM 系统子服务已停止")

    def _init_context_managers(self):
        """为启用了历史的角色创建上下文管理器"""
        for role_name, role_config in self.roles.items():
            if role_config.enable_history:
                self.context_managers[role_name] = ContextManager(
                    max_length=role_config.max_context_length,
                )

    def reload_roles(self):
        """重新加载所有角色（保留历史记录）"""
        logger.info("重新加载角色配置")
        old_roles = self.roles.copy()
        # 保存旧的历史记录
        old_contexts = {}
        for role_name, ctx in self.context_managers.items():
            old_contexts[role_name] = {
                'history': ctx.history.copy(),
                'last_interaction': ctx.last_interaction
            }

        # 清空并重新加载
        self.context_managers.clear()
        self.client_pool.clear()
        self.role_loader.load_all_roles()
        self.roles = self.role_loader.get_roles()
        logger.info(f"重新加载后角色: {list(self.roles.keys())}")
        self._init_context_managers()

        # 恢复历史记录
        for role_name, ctx in self.context_managers.items():
            if role_name in old_contexts:
                old_role = old_roles.get(role_name)
                new_role = self.roles.get(role_name)
                if (
                    old_role
                    and new_role
                    and old_role.enable_knowledge_base != new_role.enable_knowledge_base
                ):
                    logger.info("角色 '%s' 切换知识库状态，已清除旧历史", role_name)
                    continue
                ctx.history = old_contexts[role_name]['history']
                ctx.last_interaction = old_contexts[role_name]['last_interaction']
                logger.debug(f"恢复角色 '{role_name}' 的历史记录: {len(ctx.history)} 条")

    def clear_history(self):
        """清除所有角色的对话历史记录"""
        logger.info("正在清除所有角色的对话历史记录...")
        count = 0
        for role_name, manager in self.context_managers.items():
            manager.clear()
            count += 1
        logger.info(f"已清除 {count} 个角色的对话历史记录")

    def detect_role(self, text: str) -> Tuple[Optional[RoleConfig], str]:
        """检测文本是否匹配某个角色前缀

        Args:
            text: 输入文本

        Returns:
            (role_config, content) - role_config 是 RoleConfig 对象，content 是去除前缀后的文本
        """
        return self.role_detector.detect(text)

    def process(
        self,
        role_config: RoleConfig,
        content: str,
        matched_hotwords=None,
        callback=None,
        context_manager=None,
        selection_text_override=None,
        clipboard_text_override=None,
        stop_event=None,
    ) -> Tuple[str, int, float]:
        """执行实际的 LLM 模型调用（内部方法）

        Args:
            role_config: 角色配置对象
            content: 去除前缀后的输入内容
            matched_hotwords: [(hotword, score), ...] 来自 hot_phoneme 的检索结果
            callback: 流式输出的回调函数

        Returns:
            (处理后的文本, 输出token数, 生成时间秒)
        """
        # 获取中断检查函数
        should_stop_check = lambda: self.monitor.should_stop(stop_event)
        # 获取处理后的角色名称（空字符串 -> '默认'）
        role_name = role_config.display_name or RoleConfig.DEFAULT_ROLE_NAME
        logger.debug(f"开始 LLM 核心处理 [角色: {role_name}] [内容长度: {len(content)}]")

        # 获取上下文管理器（如果启用历史）
        if context_manager is None:
            context_manager = self.context_managers.get(role_name) if role_config.enable_history else None
        if context_manager:
            logger.debug(f"角色 '{role_name}' 启用历史，当前历史条数: {len(context_manager.history)}")
        
        # 知识库模式只允许本地资料作为事实来源，不读取选区或剪贴板。
        if role_config.enable_knowledge_base:
            clipboard_text = ""
            selection_text = ""
        elif selection_text_override is not None or clipboard_text_override is not None:
            clipboard_text = clipboard_text_override if role_config.enable_read_clipboard else ""
            if clipboard_text:
                max_length = int(getattr(role_config, 'clipboard_max_length', 20000))
                clipboard_text = clipboard_text[:max_length] if max_length > 0 else clipboard_text
                selection_text = ""
            else:
                selection_text = selection_text_override if role_config.enable_read_selection else ""
                max_length = int(getattr(role_config, 'selection_max_length', 1000))
                selection_text = selection_text[:max_length] if max_length > 0 else selection_text
        else:
            # 明确说出剪贴板关键词时优先读取剪贴板，不再模拟 Ctrl+C 覆盖它
            clipboard_text = get_clipboard_text(role_config, content)
            selection_text = "" if clipboard_text else get_selected_text(role_config, self.app.state)
        knowledge_result = self.knowledge_base.retrieve(role_config, content)
        
        # 构建消息
        messages = self.message_builder.build_messages(
            role_config, content, context_manager,
            hotwords=matched_hotwords,
            selection_text=selection_text,
            clipboard_text=clipboard_text,
            knowledge_base_text=knowledge_result.content,
        )
        
        # 使用 LLM 处理引擎执行请求
        result_text, token_count, gen_time = self.processor.process(
            role_config=role_config,
            messages=messages,
            callback=callback,
            should_stop_check=should_stop_check,
            context_manager=context_manager
        )

        # 原文附录由本地程序直接拼接，不经过模型，避免改写或概括。
        if role_config.enable_knowledge_base and knowledge_result.evidence:
            evidence_appendix = format_evidence_appendix(knowledge_result.evidence)
            if callback:
                callback(evidence_appendix)
            result_text = f"{result_text}{evidence_appendix}"

        # 记录选中文字的使用（用于下一轮判断是否重复）
        record_selection_usage(role_config, selection_text)

        return result_text, token_count, gen_time

    async def process_and_output(self, text: str, paste: bool = None, matched_hotwords=None) -> Optional[LLMResult]:
        """
        统一入口：处理输入文本并根据配置执行输出（打字或弹屏）
        
        Args:
            text: 待润色的完整原始文本（含可能的前缀）
            paste: 是否强制使用粘贴模式（None 则遵循配置）
            matched_hotwords: 潜在热词列表
        """
        import time
        from .llm_output_typing import handle_typing_mode, output_text
        from .llm_output_toast import handle_toast_mode
        from core.client.output.text_output import TextOutput

        start_time = time.time()
        # 重置中断标志
        self.monitor.reset()
        
        # 1. 角色检测
        role_config, content = self.detect_role(text)

        # 2. 如果不匹配任何需要处理的角色
        if not role_config:

            # 打字输出
            await output_text(text, paste)
            
            # 更新全局状态并 UDP 广播
            self.app.state.set_output_text(text)
            broadcast_output_udp(text)

            return LLMResult(result=text, role_name=None, processed=False, 
                                token_count=0, polish_time=0, input_text=text)


        # 3. 并行子角色：本角色与子角色同时处理，各自 Toast 显示
        if role_config.parallel_roles:
            return await self._process_parallel_roles(text, role_config, content, matched_hotwords)

        # 4. 根据输出模式分发处理
        if role_config.output_mode == 'toast':
            result, token_count, gen_time = await handle_toast_mode(self, text, role_config, matched_hotwords, content)
        else: # typing
            result, token_count, gen_time = await handle_typing_mode(self, text, paste, matched_hotwords, role_config, content)

        # 5. 后置处理
        # 更新全局状态（即便是中断了，也记录已经输出的部分）
        if result:
            self.app.state.set_output_text(result)
            broadcast_output_udp(result)

        return LLMResult(
            result=result,
            role_name=role_config.display_name or RoleConfig.DEFAULT_ROLE_NAME,
            processed=True,
            token_count=token_count,
            polish_time=time.time() - start_time,
            input_text=content,
            generation_time=gen_time
        )

    async def _process_parallel_roles(
        self, text: str, role_config: RoleConfig, content: str, matched_hotwords=None
    ) -> Optional[LLMResult]:
        """并行处理本角色与 parallel_roles 子角色，各自 Toast 显示，返回合并结果"""
        import time
        from .llm_output_toast import handle_toast_mode

        start_time = time.time()
        from core.tools.asyncio_to_thread import to_thread
        shared_clipboard, shared_selection = await to_thread(
            self._read_parallel_context,
            role_config,
            content,
        )
        sub_configs = []
        for name in self._normalize_parallel_role_names(role_config.parallel_roles):
            sub = self.roles.get(name)
            if sub is None:
                logger.warning("并行子角色不存在: %s", name)
                continue
            if sub.parallel_roles:
                logger.warning("子角色 '%s' 不允许嵌套 parallel_roles，已跳过", name)
                continue
            sub_configs.append(sub)

        parallel_configs = [role_config, *sub_configs]
        names = [config.display_name or RoleConfig.DEFAULT_ROLE_NAME for config in parallel_configs]
        group_id = uuid.uuid4().hex if len(parallel_configs) > 1 else None
        group_gap = max(0, int(getattr(role_config, 'parallel_gap', 0)))
        tasks = [
            handle_toast_mode(
                self,
                text,
                config,
                matched_hotwords,
                content,
                group_id=group_id,
                group_index=index,
                group_size=len(parallel_configs),
                group_gap=group_gap,
                selection_text_override=shared_selection,
                clipboard_text_override=shared_clipboard,
                reset_monitor=False,
            )
            for index, config in enumerate(parallel_configs)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        if group_id:
            from core.ui.toast import ToastMessageManager
            ToastMessageManager().request_finalize_group(group_id)

        parts, total_tokens, max_gen = [], 0, 0.0
        for name, result in zip(names, results):
            if isinstance(result, BaseException):
                logger.error("并行角色 '%s' 处理失败: %s", name, result)
                continue
            result_text, token_count, gen_time = result
            total_tokens += token_count
            max_gen = max(max_gen, gen_time)
            if result_text:
                parts.append(f"【{name}】{result_text}")

        return LLMResult(
            result="\n\n".join(parts),
            role_name=role_config.display_name or RoleConfig.DEFAULT_ROLE_NAME,
            processed=True,
            token_count=total_tokens,
            polish_time=time.time() - start_time,
            input_text=content,
            generation_time=max_gen,
        )

    def _read_parallel_context(self, role_config: RoleConfig, content: str) -> tuple[str, str]:
        """并行组只读取一次剪贴板/选区，避免多个角色竞争 Ctrl+C。"""
        if role_config.enable_knowledge_base:
            return "", ""
        clipboard_text = get_clipboard_text(role_config, content)
        selection_text = "" if clipboard_text else get_selected_text(role_config, self.app.state)
        return clipboard_text, selection_text

    @staticmethod
    def _normalize_parallel_role_names(values) -> list[str]:
        """兼容元组、列表和逗号分隔字符串的并行角色写法。"""
        if isinstance(values, str):
            values = (values,)
        names = []
        for value in values or ():
            names.extend(
                name.strip()
                for name in re.split(r'[,，]', str(value))
                if name.strip()
            )
        return names


# ======================================================================
# --- 测试 ---

if __name__ == "__main__":
    print("=" * 60)
    print("LLM 处理器 - 测试模式")
    print("=" * 60)

    import asyncio
    from core.client.state import ClientState
    from types import SimpleNamespace

    async def run_test_cases():
        # 创建一个模拟的 app 实例
        mock_app = SimpleNamespace()
        mock_app.base_dir = Path(".").resolve()

        # 模拟 hotword manager
        mock_app.hotword = SimpleNamespace()

        # 模拟 state
        mock_app.state = ClientState(mock_app)
        
        # 初始化处理器
        handler = LLMHandler(mock_app)
        handler.start()
        
        print(f"\n已加载角色: {list(handler.roles.keys())}")

        test_cases = [
            "呃，我想查看一下当前目录的文件",
            "命令 查看当前目录的文件",
            "Python 读取文件",
        ]

        print("\n--- 测试案例 ---\n")
        try:
            for test_text in test_cases:
                print(f"输入: {test_text}")
                # 注意：这里直接调用 process 而不是 process_and_output，避免依赖复杂的 UI/打字逻辑
                role_config, content = handler.detect_role(test_text)
                if role_config:
                    print(f"检测到角色: {role_config.name}")
                    # 由于是模拟环境，可能无法真正发起请求，这里仅演示逻辑
                else:
                    print("未检测到特定角色")
                print("-" * 40)
        finally:
            handler.stop()

    asyncio.run(run_test_cases())
