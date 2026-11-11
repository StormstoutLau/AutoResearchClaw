"""
模型网关 — 统一的多模型调用接口

支持:
  - DeepSeek v4 Pro (Trae 商业): 高层决策
  - GPT 120B (本地): 推理、形式化翻译、错误修复
  - Oprover 32B (本地): 高频 tactic 生成
  - 辅助模型 (本地): 错误分类、引理排序

所有模型调用通过此网关，便于统一记录、重试、超时管理。
"""

from __future__ import annotations
import os
import time
import asyncio
from typing import Optional, Callable, Any
from dataclasses import dataclass

from .datatypes import ModelCallRecord


class LLMEndpointMissingError(RuntimeError):
    """W9 / B-58 切片: `require_endpoint=True` 但 `base_url` 为空（配置错误）。"""


@dataclass
class ModelResponse:
    text: str
    model: str
    latency_ms: float
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None
    # B-32 (归因透明化): 空 content 的**原始事实** + **机读归因标签**。
    #   为什么需要: 推理型模型把 max_tokens 烧在思考链 ⇒ content 空 ⇒ 下游只见
    #   `parsed=0/5`, 无法区分「预算被思维链吃光」与「真空」(D044 差点据此触发
    #   B-13 的错误修法)。三者默认值 ⇒ **既有构造点零变化** (Mock/成功路径不变)。
    finish_reason: Optional[str] = None   # 引擎原样 (实测如 "length"/"stop"); 不可得 ⇒ None
    reasoning_chars: int = 0              # message.reasoning_content 字符数; 不可得 ⇒ 0
    diagnosis: Optional[str] = None       # 归因标签; 成功/未知 ⇒ None


# ============================================================================
# B-32: 空 content 归因 (纯函数, 无 IO —— 可离线复算)
# ============================================================================

def classify_empty_completion(finish_reason: Optional[str],
                              reasoning_chars: int) -> str:
    """空 content 的归因分类 (B-32)。返回**稳定机读标签** (非人类文案)。

    判据 (RESEARCH_B32 §2.4-D 正/负对照锁定为**合取**):
      - `finish_reason == "length"` ∧ `reasoning_chars > 0` ⇒ 预算被思维链吃光
      - `finish_reason == "length"` ∧ `reasoning_chars == 0` ⇒ 预算耗尽(无思考链)
      - 其它 ⇒ 泛化「空 content」
    ⚠ `reasoning_content` 存在**不蕴含失败** (实测: 成功响应亦可带 791 字符思考链)。
    """
    fr = (finish_reason or "").strip().lower()
    if fr == "length":
        return "budget_exhausted_by_reasoning" if reasoning_chars > 0 else "budget_exhausted"
    return "empty_content"


def _extract_reasoning_chars(message: dict) -> int:
    """取 `message.reasoning_content` 的字符数。

    **fail-closed**: 只认实测确认的键 (llama.cpp / MiniMax-M2.7 实测, RESEARCH §2.4-D);
    缺失或非 str ⇒ 0 ⇒ 归因**退化为泛化标签**, 不声称未验证的归因。
    """
    v = message.get("reasoning_content")
    return len(v) if isinstance(v, str) else 0


def _empty_error_message(diagnosis: str, finish_reason: Optional[str],
                         reasoning_chars: int) -> str:
    """按归因给人类可读错误文案 (纯 ASCII, D027)。generic 桶**保留原串**。"""
    if diagnosis == "empty_content":
        return "empty completion content"
    if diagnosis == "budget_exhausted_by_reasoning":
        return ("empty content: budget exhausted by reasoning "
                f"(finish_reason={finish_reason}, reasoning_chars={reasoning_chars})")
    return ("empty content: budget exhausted "
            f"(finish_reason={finish_reason}, reasoning_chars={reasoning_chars})")


class ModelGateway:
    """
    多模型调用网关

    实际使用时，需要根据本地 LLM 服务（LM Studio / Ollama）和 Trae API 实现
    具体的 call_* 方法。此处提供接口定义和 Mock 实现。
    """

    def __init__(self,
                 orchestrator_model: str = "DeepSeekV4Pro",
                 reasoner_model: str = "GPT120B",
                 tactician_model: str = "Oprover32B",
                 auxiliary_model: str = "aux",
                 base_url: str = "",          # "" = Mock; 非空 = 真实 LM Studio/Ollama 端点
                 llm_timeout_seconds: float = 120.0,
                 llm_max_tokens: int = 4096,
                 llm_extra_body: Optional[dict] = None,
                 require_endpoint: bool = False):
        self.orchestrator = orchestrator_model
        self.reasoner = reasoner_model
        self.tactician = tactician_model
        self.auxiliary = auxiliary_model
        self.base_url = base_url.strip().rstrip("/") if base_url else ""
        self.require_endpoint = bool(require_endpoint)
        # W9 / B-58 切片: 生产语义下缺端点 ⇒ **构造期失败**（而非静默 Mock）。
        if self.require_endpoint and not self.base_url:
            raise LLMEndpointMissingError(
                "LLM endpoint required but base_url is empty; "
                "set llm_base_url / AUTO_PROVER_LLM_BASE_URL "
                "or disable require_endpoint")
        self.llm_timeout_seconds = llm_timeout_seconds
        self.llm_max_tokens = llm_max_tokens
        # U-20 (D044): 端点特定请求参数透传 (如推理模型 {chat_template_kwargs:{enable_thinking:false}})。
        #   为什么必须可透传: 推理模型把预算烧在 reasoning_content ⇒ content 为空 ⇒ 解析 0 例;
        #   而"关思维链"的开关是**各家私有**的 JSON 字段 —— 无透传则换模型即失效。
        self.llm_extra_body = dict(llm_extra_body) if llm_extra_body else {}
        self.call_records: list[ModelCallRecord] = []

    # ========================================================================
    # 高层接口（按角色调用）
    # ========================================================================

    async def call_orchestrator(self, prompt: str, task: str,
                                temperature: float = 0.3) -> ModelResponse:
        """调用 DeepSeek v4 Pro — 策略规划、决策"""
        return await self._call(self.orchestrator, prompt, task, temperature)

    async def call_reasoner(self, prompt: str, task: str,
                            temperature: float = 0.1) -> ModelResponse:
        """调用 GPT 120B — 推理、形式化、修复"""
        return await self._call(self.reasoner, prompt, task, temperature)

    async def call_tactician(self, prompt: str, task: str,
                             temperature: float = 0.7,
                             n_samples: int = 1) -> list[ModelResponse]:
        """调用 Oprover 32B — 高频 tactic 生成，支持 Pass@k"""
        responses = []
        for i in range(n_samples):
            resp = await self._call(self.tactician, prompt,
                                    f"{task}#{i+1}", temperature)
            responses.append(resp)
        return responses

    async def call_auxiliary(self, prompt: str, task: str,
                             temperature: float = 0.05) -> ModelResponse:
        """调用辅助模型 — 错误分类、引理排序"""
        return await self._call(self.auxiliary, prompt, task, temperature)

    # ========================================================================
    # 底层调用（Mock 实现，需替换为实际 API）
    # ========================================================================

    async def _call(self, model: str, prompt: str, task: str,
                    temperature: float) -> ModelResponse:
        """
        实际模型调用

        生产环境需要替换为:
          - LM Studio: POST http://localhost:1234/v1/chat/completions
          - Ollama:    POST http://localhost:11434/api/generate
          - Trae API:  通过 MCP 工具调用 DeepSeek v4 Pro
        """
        start = time.time()

        # M1 e2e: base_url 非空 → 真实 HTTP (LM Studio/Ollama 兼容端点)
        if self.base_url:
            return await self._call_http(model, prompt, task, temperature)

        # --- Mock 实现（保留原样; base_url="" 时行为零变化）---
        try:
            # 模拟不同模型的响应延迟
            delays = {
                "DeepSeekV4Pro": 2.0,
                "GPT120B": 1.5,
                "Oprover32B": 0.3,
                "aux": 0.1,
            }
            delay = delays.get(model, 1.0)
            await asyncio.sleep(delay * 0.01)  # 实际使用时移除

            # 实际调用示例:
            # response = await self._call_lm_studio(model, prompt, temperature)
            # response = await self._call_ollama(model, prompt, temperature)
            # response = await self._call_trae_api(model, prompt, temperature)

            text = f"[{model}] Response to: {task}"
            # --- Mock 结束 ---

            latency = (time.time() - start) * 1000
            record = ModelCallRecord(
                model=model, stage="unknown", task=task,
                prompt_tokens=len(prompt) // 4,
                completion_tokens=len(text) // 4,
                latency_ms=latency, success=True
            )
            self.call_records.append(record)

            return ModelResponse(
                text=text, model=model, latency_ms=latency,
                tokens_used=len(text) // 4, success=True
            )

        except Exception as e:  # broad-ok: LLM 网关（Mock/HTTP）调用外部异常不可枚举（降级 success=False）
            latency = (time.time() - start) * 1000
            record = ModelCallRecord(
                model=model, stage="unknown", task=task,
                latency_ms=latency, success=False, error=str(e)
            )
            self.call_records.append(record)

            return ModelResponse(
                text="", model=model, latency_ms=latency,
                success=False, error=str(e)
            )

    # ========================================================================
    # HTTP 调用 (M1 e2e: LM Studio / Ollama 兼容端点)
    # ========================================================================

    async def _call_http(self, model: str, prompt: str, task: str,
                         temperature: float) -> ModelResponse:
        """真实 HTTP 调用 {base_url}/v1/chat/completions

        base_url 非空时由 _call 分派到此。失败/超时/空 content → ModelResponse
        (success=False) 降级返回, 并照记一条 ModelCallRecord (调用方可见重试/降级)。

        Note: model 直接透传 (LM Studio 吃 config 角色模型名); 4 角色同模型时
        get_stats() 会合并成单桶, 验收按 call_records 的 task 拆分统计。
        """
        import aiohttp  # 惰性导入: 默认 Mock 路径零依赖
        start = time.time()
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": self.llm_max_tokens,
        }
        # U-20 (D044): 端点特定参数透传 (后覆盖) —— 如
        #   {"chat_template_kwargs": {"enable_thinking": false}} 关掉推理模型的思维链。
        payload.update(self.llm_extra_body)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.llm_timeout_seconds),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            # B-32: 一次取出 choice/message 的**原始事实** —— 空 content 时用于归因。
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            finish_reason = choice.get("finish_reason")
            reasoning_chars = _extract_reasoning_chars(message)
            if not content:
                diagnosis = classify_empty_completion(finish_reason, reasoning_chars)
                return self._record(
                    ModelResponse(
                        text="", model=model, latency_ms=(time.time() - start) * 1000,
                        tokens_used=0, success=False,
                        error=_empty_error_message(diagnosis, finish_reason, reasoning_chars),
                        finish_reason=finish_reason, reasoning_chars=reasoning_chars,
                        diagnosis=diagnosis,
                    ),
                    prompt, task,
                )
            tokens = data.get("usage", {}).get("total_tokens", 0)
            return self._record(
                ModelResponse(text=content, model=model, latency_ms=(time.time() - start) * 1000,
                              tokens_used=tokens, success=True,
                              finish_reason=finish_reason, reasoning_chars=reasoning_chars),
                prompt, task,
            )
        except Exception as e:  # broad-ok: HTTP 端点/网络外部异常不可枚举（降级 success=False）
            return self._record(
                ModelResponse(text="", model=model, latency_ms=(time.time() - start) * 1000,
                              tokens_used=0, success=False, error=str(e)),
                prompt, task,
            )

    def _record(self, resp: ModelResponse, prompt: str, task: str) -> ModelResponse:
        """记一条 ModelCallRecord 并返回响应本身

        B-32: 若带归因标签, 追加进记录的 `error` (审计出口) —— 使「归因」被**记下**
        而非仅随返回值一闪而过。`diagnosis=None` 时 `error` **逐字不变** (零变化)。
        B-36: 同时把三归因**结构化**落进记录 (原始事实, 可机读); `getattr` 防护旧 Mock/fake
        (无此属性 ⇒ 默认), 一处修复覆盖全族 Stage 调用 (皆经此汇聚)。
        """
        record_error = resp.error
        diagnosis = getattr(resp, "diagnosis", None)
        if diagnosis:
            record_error = f"{resp.error} [diagnosis={diagnosis}]"
        self.call_records.append(ModelCallRecord(
            model=resp.model, stage="unknown", task=task,
            prompt_tokens=len(prompt) // 4,
            completion_tokens=resp.tokens_used,
            latency_ms=resp.latency_ms, success=resp.success, error=record_error,
            finish_reason=getattr(resp, "finish_reason", None),
            reasoning_chars=getattr(resp, "reasoning_chars", 0),
            diagnosis=diagnosis,
        ))
        return resp

    def diagnosis_summary(self) -> dict:
        """传输归因汇总 (B-36): 把 `call_records` 的结构化归因聚合成机读 dict。

        为什么需要: `ModelCallRecord` 三归因字段的**生产读取点** —— 无消费点即幽灵字段
        (D039)。全族 LLM 调用汇聚于 `_record`, 故一处汇总覆盖全族。

        返回 (纯内存, 无 IO):
          n_calls               — 记录总数
          n_diagnosed           — `diagnosis` 非 None 的记录数
          by_diagnosis          — 按归因标签计数 (空 ⇒ {})
          by_finish_reason      — 按 `finish_reason` 计数 (None ⇒ "none")
          total_reasoning_chars — 全部记录 `reasoning_chars` 之和
        ⚠ 暴露**原始事实** (finish_reason 原值 + 字符量), 非仅标签 ⇒ 规则变更后可离线重算
          (对齐 RESEARCH_B32 §5 对「仅枚举标签」的否决)。
        """
        by_diagnosis: dict[str, int] = {}
        by_finish_reason: dict[str, int] = {}
        total_reasoning_chars = 0
        for r in self.call_records:
            if r.diagnosis:
                by_diagnosis[r.diagnosis] = by_diagnosis.get(r.diagnosis, 0) + 1
            fr = r.finish_reason or "none"
            by_finish_reason[fr] = by_finish_reason.get(fr, 0) + 1
            total_reasoning_chars += r.reasoning_chars
        return {
            "n_calls": len(self.call_records),
            "n_diagnosed": sum(by_diagnosis.values()),
            "by_diagnosis": by_diagnosis,
            "by_finish_reason": by_finish_reason,
            "total_reasoning_chars": total_reasoning_chars,
        }

    async def _call_lm_studio(self, model: str, prompt: str,
                              temperature: float) -> ModelResponse:
        """通过 LM Studio 调用本地模型 (转发 _call_http, 由 base_url 定位服务)"""
        return await self._call_http(model, prompt, "lm_studio", temperature)

    # ========================================================================
    # 统计
    # ========================================================================

    def get_stats(self) -> dict:
        """获取模型调用统计"""
        by_model = {}
        for r in self.call_records:
            if r.model not in by_model:
                by_model[r.model] = {"calls": 0, "success": 0, "total_latency": 0}
            by_model[r.model]["calls"] += 1
            if r.success:
                by_model[r.model]["success"] += 1
            by_model[r.model]["total_latency"] += r.latency_ms

        return {
            "total_calls": len(self.call_records),
            "by_model": by_model
        }


# 全局单例
_gateway: Optional[ModelGateway] = None


def _env_base_url() -> str:
    """W3 / D14: 端点 env 覆盖（非空优先；空白串视为未设）。"""
    return os.environ.get("AUTO_PROVER_LLM_BASE_URL", "").strip()


def get_gateway(config=None) -> ModelGateway:
    global _gateway
    if _gateway is None:
        override = _env_base_url()
        if config:
            _gateway = ModelGateway(
                orchestrator_model=config.orchestrator_model,
                reasoner_model=config.reasoner_model,
                tactician_model=config.tactician_model,
                auxiliary_model=config.auxiliary_model,
                base_url=override or getattr(config, "llm_base_url", ""),
                llm_timeout_seconds=getattr(config, "llm_timeout_seconds", 120.0),
                llm_max_tokens=getattr(config, "llm_max_tokens", 4096),
                llm_extra_body=getattr(config, "llm_extra_body", None),
                require_endpoint=getattr(config, "llm_require_endpoint", False),
            )
        else:
            _gateway = ModelGateway(base_url=override)
    return _gateway