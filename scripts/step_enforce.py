#!/usr/bin/env python
"""批次绑定门禁入口（P-130 / U-1 O3 Phase 1）。

目标：回答「本次变更属于哪个批次，且该批次的 session 是否完整」，而不是
「这个 feature 曾经关联过哪个 P」。模式优先级（DESIGN §3.4）：

  1. batch      = 本提交新增 / 变更 P 行；
  2. session    = 本提交变更 session；
  3. branch     = 分支名 pNNN + P 行存在；
  4. maintenance= 仅 whitespace-only 文档改动；
  5. 其余语义性四文档改动 → 失败。

U-10 C（P-137）：batch / session / branch 三种显式声明在 P ≥ `EVIDENCE_MIN_P` 时，还须校验
该 P 最新 5/5 session 的 finalize `metadata.evidence_digest`——per-file sha256 文件表必须与
**即将提交的内容**逐字节一致（「验后改文档」由此判红）；同一 session 多次 finalize（rebind）
时末次须带 `metadata.rebind_reason`。生成侧入口 = `--doc-digest <feature>`（唯一实现）。

U-11（P-144）：合并提交（≥2 父）在 CI 逐提交循环里被跳过（变更 = 父提交并集），冲突解决时
手写进来、两父皆无的内容（evil merge）因此永久逃逸。`--check-merge <commit>` 只判这类内容：
受判路径上**同时不等于两父** ⇒ exit 1；等于任一父（干净合并）⇒ 不判（不引入并集假红）。

只读零副作用。exit 0 = 通过；1 = 违规；2 = git / 映射错误（fail-closed）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 共享纯函数模块（同目录）
import spec_map   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "docs" / "PROGRESS.md"
WIKI = ROOT / "CODE_WIKI.md"
RUNNER = ROOT / "tools" / "spec_runner" / "spec_runner.py"
SESSIONS = ROOT / "tools" / "spec_runner" / "sessions"

FEATURE_RE = re.compile(
    r"^spec/([a-z0-9-]+)/(?:[A-Z0-9_]+_)?"
    r"(?:RESEARCH|DESIGN|IMPLEMENTATION|CHECKLIST(?:_FUNC)?)\.md$")
SESSION_RE = re.compile(
    r"^tools/spec_runner/sessions/(specwf-p(\d{3})-[a-z0-9-]+)\.jsonl$")
BRANCH_RE = re.compile(r"(?:^|[/_-])p(\d{3})(?:$|[/_-])", re.I)
STEP_SEQUENCE = ("research", "design", "implement", "verify", "finalize")
BATCH_BINDING_MIN_P = 129
# U-10 C（P-137）：**内容 digest 绑定**过渡边界（独立常量，不与 129 / FINALIZE_IMPACT_MIN_P 合并）。
# 推导（预注册 §10 U-10 行 + 附录 E.1 提案 135 已被占用）：135 → 136 → **137 = 实施批自身**
# （同 P-092 `FINALIZE_IMPACT_MIN_P=92` 先例：边界取实施批编号，本批吃狗粮自证）。
# 存量零回归（E1）：151 个 specwf 批次 session（P-001~P-136）全部 < 137，且 digest 校验只作用于
# **声明 P 的 session**（per-batch 作用域），历史 session 永不重验。
# 回退 = 本常量置哨兵值（如 9999 > 全部现存 P）⇒ digest 校验整体降为观察（无红、零其他行为变更）。
EVIDENCE_MIN_P = 137
DOC_DIGEST_ALGO = "sha256"


@dataclass
class Decision:
    mode: str = ""
    pids: list[str] = field(default_factory=list)
    sessions: list[str] = field(default_factory=list)
    features: set[str] = field(default_factory=set)
    source: str = ""
    errors: list[str] = field(default_factory=list)


def _norm(path: str) -> str:
    """路径归一化：反斜杠 → 斜杠；绝对路径 → 仓内相对路径。"""
    p = (path or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    q = Path(p)
    if q.is_absolute():
        try:
            p = q.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return ""
    return p


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _read_progress(ref: str) -> str:
    """ref ∈ HEAD / INDEX / WORKTREE / <base-sha>。失败抛 RuntimeError（fail-closed）。"""
    if ref == "WORKTREE":
        try:
            return PROGRESS.read_text(encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"读 PROGRESS 失败: {e}") from e
    spec = ":docs/PROGRESS.md" if ref == "INDEX" else f"{ref}:docs/PROGRESS.md"
    r = _git(["show", spec])
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git show {spec} 失败")
    return r.stdout


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _branch() -> str:
    r = _git(["branch", "--show-current"])
    return (r.stdout or "").strip()


def _branch_pid(branch: str) -> str | None:
    m = BRANCH_RE.search(branch or "")
    return f"P-{m.group(1)}" if m else None


def _pid_num(pid: str) -> int:
    m = re.search(r"P-(\d{3})", pid or "")
    return int(m.group(1)) if m else -1


def _sessions_for_pid(pid: str) -> list[str]:
    key = pid.lower().replace("-", "")
    return sorted(p.stem for p in SESSIONS.glob(f"specwf-{key}-*.jsonl"))


# ---------------------------------------------------------------- U-10 C：内容 digest 绑定（P-137）
def _norm_bytes(data: bytes) -> bytes:
    """digest 规范化：CRLF → LF（git 规范形态）。排序与路径由调用方保证。"""
    return data.replace(b"\r\n", b"\n")


def _read_doc_bytes(rel: str, base: str | None, worktree: bool = False) -> bytes | None:
    """读文档字节：门禁侧本地模式读 **index**（即将提交的内容，I-8 同 `_read_progress`）、
    CI 模式读工作树（= checkout 出的提交）；生成侧（worktree=True）读工作树（终稿此刻）。
    失败返回 None（调用方 fail-closed）。"""
    if worktree or base:
        try:
            return _norm_bytes((ROOT / rel).read_bytes())
        except OSError:
            return None
    r = subprocess.run(["git", "show", f":{rel}"], cwd=str(ROOT), capture_output=True)
    if r.returncode != 0:
        return None
    return _norm_bytes(r.stdout)


def _digest_scope(features) -> list[str]:
    """digest 作用域 = feature 目录下**四文档命名**（与 FEATURE_RE 同一口径，非四文档不绑）。"""
    out: list[str] = []
    for feat in sorted(set(features)):
        d = ROOT / "spec" / feat
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            rel = p.relative_to(ROOT).as_posix()
            if FEATURE_RE.match(rel):
                out.append(rel)
    return out


def doc_digest(features, base: str | None = None, worktree: bool = False) -> dict:
    """生成 digest 块 `{algorithm, files:{path: sha256}}`——**唯一实现**（I-10 语义同源）。

    无 aggregate 字段：单值汇总会掩盖「哪个文件变了」，per-file digest 是「验后改文档」
    与改动定位的最小充分声明，冗余汇总 = 额外 claim 面（本仓「声明 = 重数」纪律）。
    """
    files: dict[str, str] = {}
    for rel in _digest_scope(features):
        data = _read_doc_bytes(rel, base, worktree)
        if data is None:
            raise RuntimeError(f"读文档失败（无法绑定 digest）: {rel}")
        files[rel] = hashlib.sha256(data).hexdigest()
    return {"algorithm": DOC_DIGEST_ALGO, "files": files}


def _finalize_decisions(sid: str) -> list[dict]:
    """session 内 finalize 决策（首现序）。坏行 ⇒ RuntimeError（fail-closed）。"""
    path = SESSIONS / f"{sid}.jsonl"
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"{path}:{lineno}: {e.msg}") from e
            if r.get("event") != "decision":
                continue
            inp = r.get("input") if isinstance(r.get("input"), dict) else {}
            md = inp.get("metadata") if isinstance(inp.get("metadata"), dict) else {}
            if md.get("step_id") == "finalize":
                out.append(r)
    return out


def verify_digests(d: Decision, rows: dict, base: str | None) -> tuple[int, list[str]]:
    """U-10 C 校验（per-batch 作用域）：返回 (已绑定 PID 数, 错误)。

    只作用于 batch / session / branch 三种**带文档改动的显式声明**；只校验声明 P 的
    **最新 5/5 session** 的**末次** finalize——历史 session 永不重验（承 U-2 边界纪律）。
    """
    if d.mode not in ("batch", "session", "branch"):
        return 0, []
    checked, errors = 0, []
    for pid in d.pids:
        if _pid_num(pid) < EVIDENCE_MIN_P:
            continue
        feats = (rows.get(pid) or {}).get("features") or ()
        if not feats:
            continue                                   # 已由覆盖检查报错
        sids = [s for s in _sessions_for_pid(pid) if s in d.sessions]
        if not sids:
            continue                                   # 已由完整性检查报错
        sid = sids[-1]
        try:
            finals = _finalize_decisions(sid)
        except (OSError, RuntimeError) as e:
            errors.append(f"{sid} 读取失败: {e}")
            continue
        if not finals:
            errors.append(f"{sid} 无 finalize 决策（无法绑定 digest）")
            continue
        md = (finals[-1].get("input") or {}).get("metadata") or {}
        if len(finals) >= 2 and not str(md.get("rebind_reason") or "").strip():
            errors.append(f"{sid} rebind 缺原因（末次 finalize 须带 metadata.rebind_reason）")
        dig = md.get("evidence_digest")
        if (not isinstance(dig, dict) or dig.get("algorithm") != DOC_DIGEST_ALGO
                or not isinstance(dig.get("files"), dict) or not dig["files"]):
            errors.append(f"{sid} finalize 缺/非法 evidence_digest"
                          f"（须为 {DOC_DIGEST_ALGO} 文件表；P≥{EVIDENCE_MIN_P} 必须有）")
            continue
        try:
            actual = doc_digest(feats, base)["files"]
        except RuntimeError as e:
            errors.append(f"{sid} {e}")
            continue
        declared = {str(k): str(v) for k, v in dig["files"].items()}
        missing = sorted(set(actual) - set(declared))
        extra = sorted(set(declared) - set(actual))
        if missing or extra:
            errors.append(f"{sid} digest 文件集不一致（缺 {missing} / 多 {extra}）")
            continue
        bad = [p for p in sorted(actual) if actual[p] != declared[p]]
        if bad:
            errors.append(f"{sid} digest 不匹配（验后改文档）: " + ", ".join(bad))
        checked += 1
    return checked, errors


def _run_gate(sid: str, expect: tuple[str, ...] | None = None) -> int:
    cmd = [sys.executable, str(RUNNER), "step-gate", "--session", sid]
    if expect:
        cmd += ["--expect", *expect]
    else:
        cmd += ["--legacy"]          # 内部一致性检查 = 显式 legacy（P-132）
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode


def _check_sessions(sids: list[str], require_complete: bool) -> tuple[list[str], list[str]]:
    """内部合法性对所有 session 强制；完整性只要求「至少一个 5/5」。"""
    complete, errors = [], []
    for sid in sids:
        internal = _run_gate(sid)
        if internal != 0:
            errors.append(f"session {sid} 内部不一致（step-gate exit {internal}）")
            continue
        if require_complete and _run_gate(sid, STEP_SEQUENCE) == 0:
            complete.append(sid)
    if require_complete and not complete:
        errors.append("无 5/5 完整 session")
    return complete, errors


def _local_changed() -> set[str] | None:
    """本地模式的实际变更集：暂存 ∪ 工作树（DESIGN §3.3 步 2a）。

    背景：`pre-commit run --all-files` 会把**全量**匹配文件作为 argv 传入，
    若直接按 argv 判「变更」，每次 P 行变更都会把 66 份四文档误判为改动。
    提交时 pre-commit 只传暂存文件，故求交**不削弱**门禁；git 失败返回 None（fail-closed）。
    """
    changed: set[str] = set()
    for args in (["diff", "--cached", "--name-only"],
                 ["diff", "--name-only"],
                 ["ls-files", "--others", "--exclude-standard"]):
        r = _git(args)
        if r.returncode != 0:
            return None
        changed.update(x.strip().replace("\\", "/")
                       for x in (r.stdout or "").splitlines() if x.strip())
    return changed


def _whitespace_only(docs: list[str], base: str | None) -> bool:
    """维护模式判据：仅空白 / 行尾差异。git 失败按非维护处理（fail-closed）。"""
    if not docs:
        return False
    args = (["diff", f"{base}...HEAD"] if base else ["diff", "--cached"])
    args += ["-w", "--ignore-blank-lines", "--"] + docs
    r = _git(args)
    if r.returncode != 0:
        return False
    return not (r.stdout or "").strip()


# ---------------------------------------------------------------- U-11：evil merge 内容检测（P-144）
# 受判路径集：与 CI 逐提交循环的 `git diff --name-only` 过滤完全一致
# （合并面只在这三条路径上兜底；其余文件本就不进本门禁）。
JUDGED_PATHS = ("spec/**", "tools/spec_runner/sessions/**", "docs/PROGRESS.md")


def _parents(sha: str) -> list[str] | None:
    """父提交列表；git 失败返回 None（调用方 fail-closed）。"""
    r = _git(["rev-list", "--parents", "-n", "1", sha])
    if r.returncode != 0:
        return None
    return (r.stdout or "").split()[1:]


def _same(ref_a: str, ref_b: str, path: str) -> bool | None:
    """该路径在两棵树中逐字节相同？git 失败返回 None（fail-closed）。"""
    r = _git(["diff", "--quiet", ref_a, ref_b, "--", path])
    if r.returncode == 0:
        return True
    if r.returncode == 1:
        return False
    return None


def check_merge(sha: str) -> int:
    """U-11 / P-144：合并提交的 evil 内容检测（只判逐提交通道覆盖不到的那部分）。

    evil 定义（DESIGN §14.7）：合并结果在某受判路径上**同时不等于两个父提交**——
    即冲突解决时手写进来、不属于任一父的变更。干净合并（等于任一父）不判，
    故不产生 P-140 那类「并集当单一变更集」的结构性假红。
    """
    parents = _parents(sha)
    if parents is None:
        print(f"step-enforce: git error: 无法解析 {sha} 的父提交", file=sys.stderr)
        return 2
    if len(parents) < 2:
        print(f"step-enforce: {sha} 非合并提交（跳过 evil 检测）")
        return 0
    p1, p2 = parents[0], parents[1]
    r = _git(["diff", "--name-only", p1, sha, "--", *JUDGED_PATHS])
    if r.returncode != 0:
        print(f"step-enforce: git error: 无法计算 {p1}..{sha} 变更集", file=sys.stderr)
        return 2
    names = [x for x in (r.stdout or "").splitlines() if x.strip()]
    evil: list[str] = []
    for f in names:
        eq1, eq2 = _same(p1, sha, f), _same(p2, sha, f)
        if eq1 is None or eq2 is None:
            print(f"step-enforce: git error: 无法比较 {f}", file=sys.stderr)
            return 2
        if eq1 or eq2:
            continue                     # 等于任一父 ⇒ 干净合并（该父已被逐提交覆盖）
        evil.append(f)
    if not evil:
        print(f"step-enforce: merge {sha} 无 evil 内容"
              f"（{len(names)} 个受判路径均等于某一父）")
        return 0
    for f in evil:
        print(f"step-enforce: evil merge 内容（两父皆无）: {f}", file=sys.stderr)
    print(f"step-enforce: evil merge {sha} -> exit 1"
          f"（该内容须由后续声明批次承载）", file=sys.stderr)
    return 1


def _resolve_declared(d: Decision, docs_features: set[str], rows: dict) -> None:
    allowed: set[str] = set()
    for pid in d.pids:
        row = rows.get(pid)
        if not row:
            d.errors.append(f"{pid} 不在 PROGRESS")
            continue
        if not row["features"]:
            d.errors.append(f"{pid} 未声明任何 spec/<feature>/ 链接")
            continue
        allowed.update(row["features"])
    if d.errors:
        return
    missing = sorted(docs_features - allowed)
    if missing:
        d.errors.append("变更 feature 未被声明 P 覆盖: " + ", ".join(missing))
        return
    d.features = allowed
    for pid in d.pids:
        sids = _sessions_for_pid(pid)
        if not sids:
            d.errors.append(f"{pid} 无 session")
            continue
        complete, errs = _check_sessions(sids, require_complete=True)
        d.errors += errs
        d.sessions += complete


def _resolve_maintenance(d: Decision, docs_features: set[str], new_progress: str) -> None:
    mapping = spec_map.build_pid_map(new_progress, _read_text(WIKI))
    d.features = set(docs_features)
    pids: set[str] = set()
    for feat in sorted(docs_features):
        pid = mapping.get(feat)
        if not pid:
            d.errors.append(f"feature {feat} 无 feature→P 映射")
            continue
        pids.add(pid)
        sids = _sessions_for_pid(pid)
        if _pid_num(pid) >= BATCH_BINDING_MIN_P:
            if not sids:
                d.errors.append(f"{pid} 无 session（维护模式要求完整链）")
                continue
            complete, errs = _check_sessions(sids, require_complete=True)
            d.errors += errs
            d.sessions += complete
        elif sids:
            _, errs = _check_sessions(sids, require_complete=False)
            d.errors += errs
    d.pids = sorted(pids)


def resolve(changed_docs: list[str], changed_sessions: list[tuple[str, str]],
            progress_changed: bool, old_progress: str, new_progress: str,
            branch: str, whitespace_only: bool) -> Decision:
    docs_features = {m.group(1) for f in changed_docs
                     for m in [FEATURE_RE.match(f)] if m}
    rows = spec_map.parse_progress_rows(new_progress)
    declared = spec_map.changed_pids(old_progress, new_progress) if progress_changed else []
    d = Decision()

    if docs_features:
        if declared:
            d.mode, d.pids, d.source = "batch", declared, "P-row"
        elif changed_sessions:
            d.mode = "session"
            d.pids = sorted({pid for _, pid in changed_sessions})
            d.source = "session"
        else:
            bp = _branch_pid(branch)
            if bp and bp in rows:
                d.mode, d.pids, d.source = "branch", [bp], "branch"
            elif whitespace_only:
                d.mode, d.source = "maintenance", "whitespace"
            else:
                d.errors.append(
                    "语义性四文档改动缺少批次声明（新 P 行 / 变更 session / 分支名）")
                return d
        if d.mode == "maintenance":
            _resolve_maintenance(d, docs_features, new_progress)
        else:
            _resolve_declared(d, docs_features, rows)
        return d

    if changed_sessions:
        d.mode, d.source = "session-progress", "session"
        d.pids = sorted({pid for _, pid in changed_sessions})
        d.sessions = [sid for sid, _ in changed_sessions]
        _, errs = _check_sessions(d.sessions, require_complete=False)
        d.errors += errs
        return d

    if progress_changed and declared:
        d.mode, d.source = "batch-registration", "P-row"
        d.pids = declared
        for pid in declared:
            row = rows.get(pid)
            if not row:
                d.errors.append(f"{pid} 不在 PROGRESS")
            elif _pid_num(pid) >= BATCH_BINDING_MIN_P and not row["features"]:
                d.errors.append(f"{pid} 未声明任何 spec/<feature>/ 链接")
        return d

    d.mode = "nothing"
    return d


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="step_enforce")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--base", help="CI 模式：旧 PROGRESS 的 git ref")
    ap.add_argument("--branch", help="CI 模式：分支名（默认读当前分支）")
    ap.add_argument("--doc-digest", action="append", default=None, metavar="FEATURE",
                    help="U-10 C：打印 feature 四文档 sha256 绑定块（粘贴进 finalize "
                         "metadata.evidence_digest；可重复指定 feature）")
    ap.add_argument("--check-merge", metavar="COMMIT",
                    help="U-11 / P-144：检测合并提交是否引入两父皆无的内容（evil merge；"
                         "只判 spec/**、sessions、PROGRESS 三条受判路径）")
    args = ap.parse_args(argv)

    if args.check_merge:
        return check_merge(args.check_merge)

    if args.doc_digest:
        try:
            block = doc_digest(args.doc_digest, worktree=True)  # 生成侧读工作树（终稿此刻）
        except RuntimeError as e:
            print(f"step-enforce: {e}", file=sys.stderr)
            return 2
        print(json.dumps(block, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    files = [_norm(f) for f in args.files]
    if not args.base:
        changed = _local_changed()
        if changed is None:
            print("step-enforce: git error: 无法计算本地变更集", file=sys.stderr)
            return 2
        # 本地模式以 git 实际变更集为准：pre-commit 会按块传参（单次 argv 可能只是
        # 四文档子集），若信 argv 会把「同一次提交的声明」分块误判（DESIGN §3.3 步 2）。
        files = [f for f in changed
                 if FEATURE_RE.match(f) or SESSION_RE.match(f)
                 or f == "docs/PROGRESS.md"]
    docs = [f for f in files if FEATURE_RE.match(f)]
    sessions = []
    for f in files:
        m = SESSION_RE.match(f)
        if m:
            sessions.append((m.group(1), f"P-{m.group(2)}"))
    progress_changed = "docs/PROGRESS.md" in files
    if not docs and not sessions and not progress_changed:
        return 0

    try:
        old = _read_progress(args.base) if args.base else _read_progress("HEAD")
        new = _read_progress("WORKTREE") if args.base else _read_progress("INDEX")
    except RuntimeError as e:
        print(f"step-enforce: git error: {e}", file=sys.stderr)
        return 2

    branch = args.branch or _branch()
    d = resolve(docs, sessions, progress_changed, old, new, branch,
                _whitespace_only(docs, args.base))
    checked, digest_errors = 0, []
    if not d.errors:      # 声明 / 覆盖 / 完整性已红时不叠加 digest 噪声（同一次修复即可）
        checked, digest_errors = verify_digests(
            d, spec_map.parse_progress_rows(new), args.base)
        d.errors += digest_errors
    if d.errors:
        for e in d.errors:
            print(f"step-enforce: {e}", file=sys.stderr)
        print(f"step-enforce: mode={d.mode} pid={','.join(d.pids) or '-'} -> exit 1",
              file=sys.stderr)
        return 1
    print(f"step-enforce: mode={d.mode} pid={','.join(d.pids) or '-'} "
          f"sessions={','.join(d.sessions) or '-'} "
          f"features={','.join(sorted(d.features)) or '-'} source={d.source}")
    if checked:
        print(f"step-enforce: digest_bound={checked}（P≥{EVIDENCE_MIN_P} finalize "
              f"{DOC_DIGEST_ALGO} 文件表与提交内容一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
