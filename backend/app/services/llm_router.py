"""
app/services/llm_router.py
共享 LLM 路由器 —— 多 Key 轮询 + 每槽 Semaphore 限流 + 熔断器

被 intent_parser 和 explanation_builder 共同使用，避免重复创建路由实例。
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    轮询多个 (url, key, model) 槽位，每个槽位独立 Semaphore 限流。
    - 429（限流）→ 切换下一槽位（可重试）
    - 超时 / 网络异常 → 切换下一槽位
    - 4xx 非限流 → 熔断：连续失败 N 次后冷却，期间直接跳过
    - 所有槽位均不可用时返回 None，由调用方降级处理
    """

    _CONCURRENCY_PER_SLOT = 3      # 每个 Key 允许的最大并发调用数（避免单Key排队积压）
    _CIRCUIT_BREAK_AFTER  = 3      # 连续非限流 4xx 达到此值触发熔断
    _CIRCUIT_COOLDOWN     = 120.0  # 熔断冷却时长（秒）

    def __init__(self, providers: list[dict]) -> None:
        self._providers = providers
        self._semaphores: list[asyncio.Semaphore] | None = None
        self._current_idx: int = 0
        self._consec_errors: dict[int, int]   = {}
        self._dead_until:    dict[int, float] = {}

    def _ensure_init(self) -> None:
        if self._semaphores is None:
            self._semaphores = [
                asyncio.Semaphore(self._CONCURRENCY_PER_SLOT)
                for _ in self._providers
            ]

    def _next_start_idx(self) -> int:
        idx = self._current_idx
        self._current_idx = (self._current_idx + 1) % max(len(self._providers), 1)
        return idx

    def _is_alive(self, idx: int) -> bool:
        deadline = self._dead_until.get(idx, 0.0)
        if deadline == 0.0:
            return True
        if _time.monotonic() >= deadline:
            self._dead_until[idx] = 0.0
            self._consec_errors[idx] = 0
            logger.info("LLM 槽位 %d (%s) 熔断冷却结束，恢复可用",
                        idx, self._providers[idx]["model"])
            return True
        return False

    def _record_fatal_error(self, idx: int, status: int) -> None:
        count = self._consec_errors.get(idx, 0) + 1
        self._consec_errors[idx] = count
        if count >= self._CIRCUIT_BREAK_AFTER:
            self._dead_until[idx] = _time.monotonic() + self._CIRCUIT_COOLDOWN
            logger.warning(
                "LLM 槽位 %d (%s) 连续 %d 次返回 HTTP %d，熔断 %.0f 秒",
                idx, self._providers[idx]["model"], count, status, self._CIRCUIT_COOLDOWN,
            )

    def _record_success(self, idx: int) -> None:
        self._consec_errors[idx] = 0

    @property
    def has_providers(self) -> bool:
        return bool(self._providers)

    @property
    def slot_count(self) -> int:
        return len(self._providers)

    async def call(
        self,
        prompt: str,
        timeout: float = 15.0,
        max_tokens: int = 120,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        发起 LLM 调用，自动轮询所有槽位。
        
        参数:
            prompt: 用户提示词
            timeout: 单次请求超时（秒），默认 15s
            max_tokens: 最大输出 token 数，默认 120（足够短文本）
            temperature: 温度，默认 0.7
        
        返回:
            LLM 输出文本，失败返回 None
        """
        if not self._providers:
            return None
        self._ensure_init()

        n = len(self._providers)
        start = self._next_start_idx()

        for i in range(n):
            idx = (start + i) % n

            if not self._is_alive(idx):
                logger.debug("LLM 槽位 %d (%s) 熔断中，跳过",
                             idx, self._providers[idx]["model"])
                continue

            provider = self._providers[idx]
            sem = self._semaphores[idx]  # type: ignore[index]

            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(
                            f"{provider['url']}/chat/completions",
                            headers={"Authorization": f"Bearer {provider['key']}"},
                            json={
                                "model": provider["model"],
                                "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": max_tokens,
                                "temperature": temperature,
                            },
                        )
                        if resp.status_code == 429:
                            logger.debug("LLM 槽位 %d (%s) 触发限流，切换到下一槽位",
                                         idx, provider["model"])
                            continue
                        if 400 <= resp.status_code < 500:
                            logger.debug("LLM 槽位 %d (%s) 返回 HTTP %d，记录熔断计数",
                                         idx, provider["model"], resp.status_code)
                            self._record_fatal_error(idx, resp.status_code)
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                        self._record_success(idx)
                        return data["choices"][0]["message"]["content"].strip()
                except httpx.TimeoutException:
                    logger.debug("LLM 槽位 %d (%s) 超时（%.1fs），切换到下一槽位",
                                 idx, provider["model"], timeout)
                    continue
                except Exception as exc:
                    logger.debug("LLM 槽位 %d (%s) 调用失败: %s",
                                 idx, provider["model"], exc)
                    continue

        logger.debug("所有 LLM 槽位均不可用，将由调用方降级")
        return None


# ── 模块级单例，所有服务共享 ──────────────────────────────
router = LLMRouter(config.LLM_PROVIDERS)
