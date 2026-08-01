"""Local TXT/Markdown knowledge-base retrieval for LLM roles."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from . import logger
from .llm_role_config import RoleConfig


SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown"}
INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*]')
ASCII_WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
HAN_RUN_RE = re.compile(r"[\u3400-\u9fff]+")


def format_evidence_appendix(evidence: str) -> str:
    """Wrap verbatim local evidence for display after the model answer."""
    if not evidence:
        return ""
    return (
        "\n\n---\n\n"
        "## 知识库相关原文（未经模型修改）\n\n"
        f"{evidence}"
    )


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    index: int
    text: str


@dataclass(frozen=True)
class KnowledgeResult:
    content: str
    folder: Path
    evidence: str = ""
    sources: Tuple[str, ...] = ()
    file_count: int = 0
    chunk_count: int = 0
    status: str = "disabled"


@dataclass
class _CacheEntry:
    signature: Tuple[Tuple[str, int, int], ...]
    chunks: List[KnowledgeChunk]
    file_count: int
    total_chars: int


class KnowledgeBaseRetriever:
    """Load, cache and search role-specific local knowledge files."""

    def __init__(self):
        self._cache: Dict[str, _CacheEntry] = {}

    def retrieve(self, role_config: RoleConfig, query: str) -> KnowledgeResult:
        folder = self.resolve_folder(role_config)
        if not role_config.enable_knowledge_base:
            return KnowledgeResult(content="", folder=folder)

        folder.mkdir(parents=True, exist_ok=True)
        files = list(self._iter_files(folder))
        if not files:
            return KnowledgeResult(
                content="知识库文件夹中没有可读取的 TXT 或 Markdown 文件。",
                folder=folder,
                status="empty",
            )

        entry = self._get_entry(folder, files, role_config)
        if not entry.chunks:
            return KnowledgeResult(
                content="知识库文件存在，但没有读取到可用文字。",
                folder=folder,
                file_count=entry.file_count,
                status="empty",
            )

        max_chars = max(1000, int(role_config.knowledge_base_max_chars))
        if entry.total_chars <= max_chars:
            selected = entry.chunks
        else:
            selected = self._search(
                entry.chunks,
                query,
                max(1, int(role_config.knowledge_base_top_k)),
            )

        content, included = self._format_chunks(selected, max_chars)
        evidence_candidates = self._search(
            entry.chunks,
            query,
            max(1, int(role_config.knowledge_base_evidence_top_k)),
            max(0.0, min(1.0, float(role_config.knowledge_base_evidence_score_ratio))),
        )
        evidence, _ = self._format_chunks(
            evidence_candidates,
            max(1000, int(role_config.knowledge_base_evidence_max_chars)),
            preserve_first=True,
        )
        sources = tuple(dict.fromkeys(chunk.source for chunk in included))
        logger.info(
            "[知识库] 角色=%s 文件=%d 命中片段=%d 来源=%s",
            role_config.display_name or RoleConfig.DEFAULT_ROLE_NAME,
            entry.file_count,
            len(included),
            ", ".join(sources) if sources else "无",
        )
        return KnowledgeResult(
            content=content or "知识库中没有找到与问题相关的内容。",
            folder=folder,
            evidence=evidence,
            sources=sources,
            file_count=entry.file_count,
            chunk_count=len(included),
            status="ok" if content else "no_match",
        )

    @staticmethod
    def resolve_folder(role_config: RoleConfig) -> Path:
        from config_client import BASE_DIR

        configured = str(role_config.knowledge_base_folder or "").strip()
        if configured:
            folder = Path(configured).expanduser()
            return folder if folder.is_absolute() else Path(BASE_DIR) / folder

        role_name = role_config.display_name or RoleConfig.DEFAULT_ROLE_NAME
        safe_name = INVALID_FOLDER_CHARS.sub("_", role_name).rstrip(" .") or RoleConfig.DEFAULT_ROLE_NAME
        return Path(BASE_DIR) / "LLM知识库" / safe_name

    @staticmethod
    def _iter_files(folder: Path) -> Iterable[Path]:
        for path in sorted(folder.rglob("*"), key=lambda item: str(item).lower()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                yield path

    def _get_entry(
        self,
        folder: Path,
        files: Sequence[Path],
        role_config: RoleConfig,
    ) -> _CacheEntry:
        signature = tuple(
            (str(path.relative_to(folder)), path.stat().st_size, path.stat().st_mtime_ns)
            for path in files
        )
        cache_key = str(folder.resolve()).lower()
        cached = self._cache.get(cache_key)
        if cached and cached.signature == signature:
            return cached

        chunks: List[KnowledgeChunk] = []
        max_file_bytes = max(1024, int(role_config.knowledge_base_max_file_bytes))
        chunk_chars = max(300, int(role_config.knowledge_base_chunk_chars))
        for path in files:
            relative = str(path.relative_to(folder))
            if path.stat().st_size > max_file_bytes:
                logger.warning("[知识库] 跳过超大文件: %s", relative)
                continue
            try:
                text = self._read_text(path)
            except Exception as exc:
                logger.warning("[知识库] 无法读取 %s: %s", relative, exc)
                continue
            for index, chunk_text in enumerate(self._split_text(text, chunk_chars), start=1):
                chunks.append(KnowledgeChunk(relative, index, chunk_text))

        entry = _CacheEntry(
            signature=signature,
            chunks=chunks,
            file_count=len(files),
            total_chars=sum(len(chunk.text) for chunk in chunks),
        )
        self._cache[cache_key] = entry
        return entry

    @staticmethod
    def _read_text(path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return data.decode(encoding).replace("\x00", "").strip()
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace").replace("\x00", "").strip()

    @staticmethod
    def _split_text(text: str, chunk_chars: int) -> List[str]:
        # Blank-line separated paragraphs are the retrieval unit. Keeping each
        # unit intact lets the evidence appendix reproduce source text verbatim.
        return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        lowered = text.lower()
        tokens = ASCII_WORD_RE.findall(lowered)
        for run in HAN_RUN_RE.findall(lowered):
            tokens.extend(run)
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
        return tokens

    @classmethod
    def _search(
        cls,
        chunks: Sequence[KnowledgeChunk],
        query: str,
        top_k: int,
        relative_score_ratio: float = 0.0,
    ) -> List[KnowledgeChunk]:
        query_tokens = set(cls._tokenize(query))
        if not query_tokens:
            return list(chunks[:top_k])

        chunk_tokens = [cls._tokenize(f"{chunk.source} {chunk.text}") for chunk in chunks]
        document_frequency = {
            token: sum(1 for tokens in chunk_tokens if token in set(tokens))
            for token in query_tokens
        }
        total = len(chunks)
        discriminative_tokens = {
            token for token in query_tokens
            if 0 < document_frequency[token] < total
        }
        scoring_tokens = discriminative_tokens or query_tokens
        scored = []
        for position, (chunk, tokens) in enumerate(zip(chunks, chunk_tokens)):
            counts = {token: tokens.count(token) for token in scoring_tokens}
            score = sum(
                (1.0 + math.log(count))
                * (math.log((total + 1) / (document_frequency[token] + 1)) + 1.0)
                for token, count in counts.items()
                if count
            )
            if query.strip().lower() in chunk.text.lower():
                score += 10.0
            scored.append((score, -position, chunk))

        matched = [item for item in sorted(scored, reverse=True) if item[0] > 0]
        if not matched:
            return list(chunks[:top_k])
        if relative_score_ratio > 0:
            minimum_score = matched[0][0] * relative_score_ratio
            matched = [item for item in matched if item[0] >= minimum_score]
        return [item[2] for item in matched[:top_k]]

    @staticmethod
    def _format_chunks(
        chunks: Sequence[KnowledgeChunk],
        max_chars: int,
        preserve_first: bool = False,
    ) -> Tuple[str, List[KnowledgeChunk]]:
        parts: List[str] = []
        included: List[KnowledgeChunk] = []
        used = 0
        for chunk in chunks:
            block = f"[来源：{chunk.source}，片段 {chunk.index}]\n{chunk.text}"
            if parts and used + len(block) + 2 > max_chars:
                break
            if not parts and len(block) > max_chars:
                if preserve_first:
                    logger.warning("[知识库] 相关原文单段超过返回上限，仍按整段返回: %s", chunk.source)
                else:
                    block = block[:max_chars]
            parts.append(block)
            included.append(chunk)
            used += len(block) + 2
        return "\n\n".join(parts), included
