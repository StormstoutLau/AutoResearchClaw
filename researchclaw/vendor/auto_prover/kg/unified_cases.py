"""unified_cases.py — 统一案例库 (Phase 5b-S2, Batch 0c)

将 Lean4CaseLibrary / CaseLibrary / A4 verdict JSONL 三类"案例"统一为
单一 schema (UnifiedCase) + JSONL 权威源 + 派生检索索引 (FAISS/TF-IDF)。

设计依据: RESEARCH_ATLAS_PHASE_5B_S2.md (Review #1) / DESIGN_ATLAS_PHASE_5B_S2.md (Review #2)
关键修正 (Review #2 CRITICAL-1/MODERATE-2): 白名单用枚举 .value(小写); UnifiedCase
序列化键名 case_id, A1 适配经 to_case_record() 输出 {id,...}。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# 成功案例白名单 — 用枚举 .value(小写), 与 verdict_writer.py 写入的 citation_label 一致
# (datatypes.py CitationLabel: formally_verified / partially_formalized / numerically_verified)
_READY_LABELS = {"formally_verified", "partially_formalized", "numerically_verified"}


def normalize_statement(s: str) -> str:
    """规范化陈述 → 跨源去重的唯一准绳 (DESIGN §2.2)

    A4 assertion 与 Lean4Case statement 经同一函数归一; 归一后一致 → 同一 case_id。
    规则:
      1) strip 首尾空白; 统一换行/制表 → 单空格; 折叠连续空白。
      2) 剥离内联数学定界符差异 (保留定界符内部内容)。
      3) 去 LaTeX 转义 (反斜杠+单字符); 折叠空白。
    """
    if s is None:
        return ""
    # strip 空白
    t = str(s).strip()
    # 折叠换行/制表为单空格
    t = t.replace("\n", " ").replace("\t", " ")
    # 剥离内联数学定界符: $...$ 与 \(...\) 保留内部内容 (断言文本语义在内部)
    t = _strip_inline_math(t)
    # 去 LaTeX 转义反斜杠+单字符控制
    t = re.sub(r"\\(?=[\\,;:{}])", "", t)
    # 折叠连续空白
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _strip_inline_math(s: str) -> str:
    """剥离 $...$ 与 \\(...\\) 定界符, 保留内部内容

    同时处理 LaTeX 转义定界符 `\\$...\\$` (A4 assertion 常见) 与裸 `$...$`,
    使两源归一一致 (Review #1 归一化唯一准绳要求)。
    """
    # \\$...\\$ (LaTeX 转义定界符, 同字符成对)
    s = re.sub(r"\\\$(.*?)\\\$", r"\1", s, flags=re.DOTALL)
    # $...$ (非贪婪)
    s = re.sub(r"\$(.*?)\$", r"\1", s, flags=re.DOTALL)
    # \(...\)
    s = re.sub(r"\\\((.+?)\\\)", r"\1", s, flags=re.DOTALL)
    return s


def make_case_id(statement: str) -> str:
    """确定性主键: "u_" + MD5(norm_text)[:16] (DESIGN §2.2)"""
    norm = normalize_statement(statement)
    return "u_" + hashlib.md5(norm.encode("utf-8")).hexdigest()[:16]


@dataclass
class UnifiedCase:
    """统一案例条目 (DESIGN §2.1)"""
    # core (三方共用, 检索锚点)
    case_id: str
    kind: str = "theorem"
    statement: str = ""
    code: str = ""
    source: str = "pipeline"  # textbook | pipeline | agent_dispatch
    # A6 增强 (可选)
    tags: list[str] = field(default_factory=list)
    success: bool = True
    proof_lines: int = 0
    # A4 溯源 (可选)
    verdict_id: str = ""
    citation_label: str = ""
    timestamp: str = ""  # ISO 时间, last-write-wins

    def __post_init__(self) -> None:
        """case_id 为空时自动由 statement 归一化生成 (确定性主键)"""
        if not self.case_id and self.statement:
            self.case_id = make_case_id(self.statement)

    def to_dict(self) -> dict:
        """序列化到 JSONL 行 (键名 case_id)"""
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "statement": self.statement,
            "code": self.code,
            "source": self.source,
            "tags": list(self.tags),
            "success": self.success,
            "proof_lines": self.proof_lines,
            "verdict_id": self.verdict_id,
            "citation_label": self.citation_label,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UnifiedCase":
        """从 JSONL 行构造 (缺省字段容错)"""
        return cls(
            case_id=d.get("case_id", ""),
            kind=d.get("kind", "theorem"),
            statement=d.get("statement", ""),
            code=d.get("code", ""),
            source=d.get("source", "pipeline"),
            tags=list(d.get("tags", [])),
            success=d.get("success", True),
            proof_lines=d.get("proof_lines", 0),
            verdict_id=d.get("verdict_id", ""),
            citation_label=d.get("citation_label", ""),
            timestamp=d.get("timestamp", ""),
        )

    def to_case_record(self) -> dict:
        """A1 适配: 输出 {id, kind, statement, code}, 兼容 CaseAdapter._to_case_record

        Review #2 MODERATE-2: _to_case_record 读 raw["id"], 而统一库序列化键名 case_id;
        此方法映射 case_id → id, 使 A1 零改动兼容。
        """
        return {
            "id": self.case_id,
            "kind": self.kind,
            "statement": self.statement,
            "code": self.code,
        }

    @classmethod
    def from_case_dict(cls, d: dict) -> "UnifiedCase":
        """A6 适配: Case.to_dict() → UnifiedCase (DESIGN §4.3)

        Case.to_dict() 键名: case_id/statement/code/kind/tags/success/proof_lines
        """
        return cls(
            case_id=d.get("case_id", ""),
            kind=d.get("kind", "theorem"),
            statement=d.get("statement", ""),
            code=d.get("code", ""),
            source="pipeline",
            tags=list(d.get("tags", [])),
            success=d.get("success", True),
            proof_lines=d.get("proof_lines", 0),
        )


class UnifiedCaseStore:
    """统一案例库: JSONL 权威源 + 派生 FAISS/TF-IDF 索引 (DESIGN §2.3/§3.1)"""

    DEFAULT_PATH = str(Path(__file__).parent.parent / "output" / "unified_cases.jsonl")

    def __init__(self, path: str = ""):
        """初始化

        Args:
            path: JSONL 权威源路径, 空时默认 `proof_pipeline/output/unified_cases.jsonl`
        """
        self.path = path or self.DEFAULT_PATH
        self._by_id: dict[str, UnifiedCase] = {}       # case_id → case
        self._faiss_index = None                        # FAISS 索引 (P2, 懒加载)
        self._faiss_ids: list[str] = []                 # FAISS 序号 → case_id
        self._embed_model = None                        # sentence-transformers (懒加载)
        self._tfidf_vectorizer = None
        self._tfidf_matrix = None
        self._use_tfidf = False
        self._dirty = False                             # P2: add 后索引过期标记
        self._loaded = False

    # ---- 落盘 ----

    def _load(self) -> None:
        """懒加载 JSONL (幂等)"""
        if self._loaded:
            return
        self._loaded = True
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    case = UnifiedCase.from_dict(d)
                    # last-write-wins: JSONL 可能含同 case_id 冗余行 (append-only 迁入/交换),
                    # 须按 timestamp 取较新者, 否则 import 后重建会退回旧值 (P0 分布式修复)
                    existing = self._by_id.get(case.case_id)
                    if existing is None or (
                        case.timestamp
                        and (not existing.timestamp or case.timestamp > existing.timestamp)
                    ):
                        self._by_id[case.case_id] = case
                except (json.JSONDecodeError, ValueError):
                    continue  # 崩溃恢复: 跳过坏行

    def _append_line(self, case: UnifiedCase) -> None:
        """追写 JSONL (append-only, 崩溃安全)"""
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(case.to_dict(), ensure_ascii=False) + "\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)

    # ---- 写 ----

    async def add(self, case: UnifiedCase) -> str:
        """写 JSONL (append-only, 幂等 by case_id, last-write-wins)

        P2: 若索引已构建, add 新/更新案例后置 `_dirty`, 下次 search 懒重建 —
        修复"新增案例检索不到"缺陷 (原索引不更新)。

        Returns: case_id
        """
        await self.to_thread_append(case)
        # 内存覆盖: 保留 timestamp 较新者
        existing = self._by_id.get(case.case_id)
        if existing is None or (not existing.timestamp and case.timestamp) or (
            case.timestamp and existing.timestamp and case.timestamp > existing.timestamp
        ):
            self._by_id[case.case_id] = case
            # 索引已建 → 标记过期 (懒重建); 未建则无需标记 (首次 search 才建)
            if self._tfidf_matrix is not None or self._faiss_index is not None:
                self._dirty = True
        return case.case_id

    async def to_thread_append(self, case: UnifiedCase) -> None:
        """同步追写 (经 asyncio.to_thread 异步调用)"""
        import asyncio
        import os as _os
        # 先加载内存态 (若未加载)
        if not self._loaded:
            self._load()
        await asyncio.to_thread(self._append_line, case)

    async def add_batch(self, cases: list[UnifiedCase]) -> int:
        """批量写 (崩溃安全, 逐条 append)"""
        for c in cases:
            await self.add(c)
        return len(cases)

    # ---- 读 ----

    async def get(self, case_id: str) -> Optional[UnifiedCase]:
        """按主键查"""
        if not self._loaded:
            self._load()
        return self._by_id.get(case_id)

    def stats(self) -> dict:
        """全量统计 (对齐 A6 CaseLibrary.stats)"""
        if not self._loaded:
            self._load()
        kinds: dict[str, int] = {}
        for c in self._by_id.values():
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
        return {
            "total_cases": len(self._by_id),
            "kinds": kinds,
            "sources": {s: 1 for s in {c.source for c in self._by_id.values()}},
        }

    def __len__(self) -> int:
        if not self._loaded:
            self._load()
        return len(self._by_id)

    # ---- 检索 ----

    async def _build_index(self) -> int:
        """从 JSONL 重建检索索引 (P2: FAISS 语义优先, TF-IDF fallback)

        与 vendor lean4_case_library 同款降级: sentence-transformers + FAISS
        IndexFlatIP 可用时用语义检索 (生产 .venv-embed 环境); 不可用则 TF-IDF
        (根测试环境, 与 DESIGN §5 "复用 vendr FAISS / TF-IDF fallback" 一致)。

        Returns: 索引向量数
        """
        if not self._loaded:
            self._load()
        cases = list(self._by_id.values())
        if not cases:
            return 0
        texts = [f"{c.kind} {c.statement}" for c in cases]
        ids = [c.case_id for c in cases]

        # 1) FAISS 语义后端 (可用时)
        try:
            import numpy as np
            if self._embed_model is None:
                from sentence_transformers import SentenceTransformer
                try:
                    self._embed_model = SentenceTransformer(
                        "all-MiniLM-L6-v2", local_files_only=True
                    )
                except Exception:  # broad-ok: 可选依赖 sentence-transformers 离线加载异常不可枚举（回退在线加载）
                    self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")
            import faiss
            emb = self._embed_model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False,
            )
            index = faiss.IndexFlatIP(int(emb.shape[1]))
            index.add(emb.astype("float32"))
            self._faiss_index = index
            self._faiss_ids = ids
            self._use_tfidf = False
            self._tfidf_matrix = None
            self._tfidf_vectorizer = None
            self._dirty = False
            return int(index.ntotal)
        except Exception:  # broad-ok: 可选后端 faiss/句向量加载异常不可枚举（降级 TF-IDF）
            # 降级 TF-IDF
            self._faiss_index = None
            self._faiss_ids = []

        # 2) TF-IDF fallback
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
            vectorizer = TfidfVectorizer(max_features=5000)
            matrix = vectorizer.fit_transform(texts)
            self._tfidf_vectorizer = vectorizer
            self._tfidf_matrix = matrix
            self._use_tfidf = True
            self._dirty = False
            return matrix.shape[0]
        except Exception:  # broad-ok: 可选依赖 scikit-learn 导入/拟合异常不可枚举（降级空索引）
            return 0

    async def search_statement(self, query: str, k: int = 3) -> list[UnifiedCase]:
        """FAISS 语义检索 (A1 复用); 索引不存在 → TF-IDF fallback

        P2: 若 `_dirty` (add 后索引过期) 或从未建索引 → 懒重建后再检索,
        保证持续回流的新案例可被检索到。
        """
        if not self._loaded:
            self._load()
        if not self._by_id:
            return []
        if self._dirty or (self._faiss_index is None and self._tfidf_matrix is None):
            await self._build_index()  # 懒重建 (add 后动态刷新)
        if self._tfidf_matrix is None and self._faiss_index is None:
            return []
        import numpy as np
        cases = list(self._by_id.values())

        if self._use_tfidf:
            q_vec = self._tfidf_vectorizer.transform([query])
            scores = np.asarray((q_vec @ self._tfidf_matrix.T).todense()).ravel()
            top_idx = scores.argsort()[::-1][:k]
            return [cases[i] for i in top_idx if scores[i] > 0]

        # FAISS 语义
        if self._embed_model is None:
            from sentence_transformers import SentenceTransformer
            try:
                self._embed_model = SentenceTransformer(
                    "all-MiniLM-L6-v2", local_files_only=True
                )
            except Exception:  # broad-ok: 可选依赖 sentence-transformers 离线加载异常不可枚举（回退在线加载）
                self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        q_emb = self._embed_model.encode([query], normalize_embeddings=True)
        _, idx = self._faiss_index.search(q_emb.astype("float32"), k)
        results = []
        for i in idx[0]:
            if i < 0 or i >= len(self._faiss_ids):
                continue
            cid = self._faiss_ids[i]
            c = self._by_id.get(cid)
            if c is not None:
                results.append(c)
        return results

    async def select_kw(self, query: str, k: int = 3) -> list[UnifiedCase]:
        """关键词检索 (A6 复用, 无向量时兜底)"""
        if not self._loaded:
            self._load()
        results = []
        ql = query.lower()
        for c in self._by_id.values():
            if ql in (c.statement + " " + c.code).lower():
                results.append(c)
                if len(results) >= k:
                    break
        return results

    async def rebuild_index(self) -> int:
        """重建索引 (P2: 双后端, 返回向量数)"""
        self._tfidf_matrix = None
        self._tfidf_vectorizer = None
        self._faiss_index = None
        self._faiss_ids = []
        self._dirty = False
        return await self._build_index()

    # ---- 分布式交换 ----

    async def export_bundle(self, dest_dir: str) -> int:
        """导出 schema 化 JSONL 交换包 (机器无关)"""
        if not self._loaded:
            self._load()
        d = Path(dest_dir)
        d.mkdir(parents=True, exist_ok=True)
        target = d / "unified_cases.jsonl"
        with open(target, "w", encoding="utf-8") as f:
            for c in self._by_id.values():
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        return len(self._by_id)

    async def import_bundle(self, src_dir: str) -> int:
        """导入交换包 + 追写权威源 + 重建索引

        幂等合并 by case_id + timestamp (last-write-wins):
          - 无现存 或 import 案例 timestamp 较新 → 采纳, 并经 add() 追写权威源 JSONL
            (P0 分布式修复: 仅改内存不落盘, 重启后 _load() 重建会丢失导入案例)。
          - 现存且较新 → 跳过 (不重复落盘, 减少权威源冗余行)。

        Returns: 实际入库 (新增/更新) 案例数
        """
        src = Path(src_dir) / "unified_cases.jsonl"
        if not src.exists():
            return 0
        if not self._loaded:
            self._load()
        imported = 0
        with open(src, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    case = UnifiedCase.from_dict(d)
                    existing = self._by_id.get(case.case_id)
                    adopt = existing is None or (
                        case.timestamp
                        and (not existing.timestamp or case.timestamp > existing.timestamp)
                    )
                    if adopt:
                        await self.add(case)  # 追写权威源 + 内存 last-write-wins
                        imported += 1
                except (json.JSONDecodeError, ValueError):
                    continue  # 崩溃恢复: 跳过坏行
        if imported:
            await self.rebuild_index()  # 立即刷新 (双后端), 亦可由 add 置 dirty 懒重建
        return imported