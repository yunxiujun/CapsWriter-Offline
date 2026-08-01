import importlib.util
import logging
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load the focused modules without importing the full desktop client dependency tree.
for package_name, package_path in (
    ("core", ROOT / "core"),
    ("core.client", ROOT / "core" / "client"),
    ("core.client.llm", ROOT / "core" / "client" / "llm"),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules[package_name] = package

sys.modules["core.client.llm"].logger = logging.getLogger("knowledge-test")
RoleConfig = load_module(
    "core.client.llm.llm_role_config",
    ROOT / "core" / "client" / "llm" / "llm_role_config.py",
).RoleConfig
load_module(
    "core.client.llm.llm_constants",
    ROOT / "core" / "client" / "llm" / "llm_constants.py",
)
KnowledgeBaseRetriever = load_module(
    "core.client.llm.llm_knowledge_base",
    ROOT / "core" / "client" / "llm" / "llm_knowledge_base.py",
)
format_evidence_appendix = KnowledgeBaseRetriever.format_evidence_appendix
KnowledgeBaseRetriever = KnowledgeBaseRetriever.KnowledgeBaseRetriever
MessageBuilder = load_module(
    "core.client.llm.llm_message_builder",
    ROOT / "core" / "client" / "llm" / "llm_message_builder.py",
).MessageBuilder


class KnowledgeBaseRetrieverTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        self.retriever = KnowledgeBaseRetriever()

    def tearDown(self):
        self.temp_dir.cleanup()

    def role(self, **changes):
        values = {
            "name": "知识库助理 | 资料助理",
            "enable_knowledge_base": True,
            "knowledge_base_folder": str(self.folder),
            "knowledge_base_max_chars": 50000,
            "knowledge_base_chunk_chars": 300,
            "knowledge_base_evidence_top_k": 2,
        }
        values.update(changes)
        return RoleConfig(**values)

    def test_disabled_role_does_not_create_folder(self):
        missing = self.folder / "missing"
        result = self.retriever.retrieve(
            self.role(enable_knowledge_base=False, knowledge_base_folder=str(missing)),
            "问题",
        )
        self.assertEqual(result.status, "disabled")
        self.assertFalse(missing.exists())

    def test_reads_txt_markdown_recursively_and_ignores_other_files(self):
        (self.folder / "说明.txt").write_text("项目代号是星河七号。", encoding="utf-8")
        nested = self.folder / "子目录"
        nested.mkdir()
        (nested / "规则.md").write_bytes("交付日期是十月十八日。".encode("gb18030"))
        (self.folder / "ignore.json").write_text('{"secret": "不应读取"}', encoding="utf-8")

        result = self.retriever.retrieve(self.role(), "项目什么时候交付")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.file_count, 2)
        self.assertIn("星河七号", result.content)
        self.assertIn("十月十八日", result.content)
        self.assertNotIn("不应读取", result.content)
        self.assertIn("子目录\\规则.md", result.content)
        self.assertIn("交付日期是十月十八日。", result.evidence)

    def test_large_knowledge_base_retrieves_relevant_chunk(self):
        (self.folder / "无关.txt").write_text("普通内容。" * 600, encoding="utf-8")
        (self.folder / "密码规则.md").write_text(
            "蓝鲸平台的恢复口令是晨星四十二，仅用于灾备演练。" * 20,
            encoding="utf-8",
        )
        role = self.role(knowledge_base_max_chars=1000, knowledge_base_top_k=2)

        result = self.retriever.retrieve(role, "蓝鲸平台恢复口令是什么")

        self.assertIn("晨星四十二", result.content)
        self.assertIn("密码规则.md", result.sources)
        self.assertLessEqual(len(result.content), 1000)

    def test_cache_refreshes_after_file_change(self):
        path = self.folder / "状态.txt"
        path.write_text("当前状态是红色。", encoding="utf-8")
        first = self.retriever.retrieve(self.role(), "当前状态")
        self.assertIn("红色", first.content)

        time.sleep(0.01)
        path.write_text("当前状态是绿色。", encoding="utf-8")
        second = self.retriever.retrieve(self.role(), "当前状态")
        self.assertIn("绿色", second.content)
        self.assertNotIn("红色", second.content)

    def test_evidence_keeps_long_paragraph_verbatim(self):
        paragraph = "原文开头。" + ("不可改写的内容" * 100) + "原文结尾。"
        (self.folder / "原文.md").write_text(paragraph, encoding="utf-8")
        result = self.retriever.retrieve(
            self.role(knowledge_base_evidence_max_chars=1000),
            "不可改写的内容",
        )
        self.assertIn(paragraph, result.evidence)
        appendix = format_evidence_appendix(result.evidence)
        self.assertIn("未经模型修改", appendix)
        self.assertIn(paragraph, appendix)


class KnowledgeBaseMessageTests(unittest.TestCase):
    def test_knowledge_mode_excludes_selection_and_clipboard(self):
        role = RoleConfig(
            name="知识库助理",
            enable_knowledge_base=True,
            system_prompt="原始角色提示词",
        )
        messages = MessageBuilder(object()).build_messages(
            role,
            "项目代号是什么",
            selection_text="外部选区秘密",
            clipboard_text="外部剪贴板秘密",
            hotwords=[("source", "外部热词秘密", 0.9)],
            knowledge_base_text="[来源：资料.md，片段 1]\n项目代号是星河七号。",
        )
        serialized = repr(messages)
        self.assertIn("事实只能来自", serialized)
        self.assertIn("星河七号", serialized)
        self.assertNotIn("外部选区秘密", serialized)
        self.assertNotIn("外部剪贴板秘密", serialized)
        self.assertNotIn("外部热词秘密", serialized)


if __name__ == "__main__":
    unittest.main()
