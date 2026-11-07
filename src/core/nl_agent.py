"""Gemini Function Calling 멀티턴 에이전트 루프 엔진.

사용자 자연어 요청을 분석하여 필요한 읽기 도구를 연속 호출하고,
필요 시 안전한 실행 제안(Proposed Actions)을 구성하여 최종 한국어 브리핑과 함께 반환한다.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import inspect
import json
from typing import Any, Optional

from core.bot_logger import get_logger
from core.nl_tools import (
    ALL_NL_TOOLS,
    NLToolContext,
    current_nl_context,
)

_log = get_logger("nl_agent")

MAX_AGENT_STEPS = 5

SYSTEM_INSTRUCTION = """당신은 'supabot' 암호화폐/국내외주식 멀티 거래소(업비트, 빗썸, 한국투자증권, 토스증권) 전문 트레이딩 AI 어시스턴트입니다.

[핵심 행동 수칙]
1. 추측하지 말고 반드시 먼저 도구(Tool)를 호출하여 실시간 데이터 및 리포트를 확인하세요.
   - 시세 확인: get_ticker_price
   - 잔고/예수금 확인: get_account_balances
   - 미체결 주문 확인: get_open_orders
   - 지표 분석: get_technical_indicators
   - 전략 템플릿 목록: get_strategy_templates
   - 예산 건전성: get_budget_health
   - 환경설정: get_user_settings
   - 손익(PnL) 종합 리포트: get_report_pnl (총 실현손익, 미실현손익, ROI)
   - 승률 및 손익비 통계: get_report_win_stats (승률, Profit Factor, 연승/연패)
   - 일별/월별 수익 내역: get_report_daily_profit, get_report_monthly_profit
   - 종목별 수익률 랭킹: get_report_roi_ranking (수익률 상위/하위 종목)
   - 전략별/거래소별 성과: get_report_strategy_performance, get_report_exchange_performance
   - 최대 낙폭(MDD) 리스크: get_report_drawdown_risk
   - 포트폴리오 자산 배분 비중: get_report_asset_allocation
   - DCA 배치 현황: get_report_dca_batches
2. 복합 작업 수행 시 논리적 순서를 지키세요:
   - "미체결 주문 취소해줘" -> 1) get_open_orders로 현재 주문 UUID 확인 -> 2) propose_cancel_orders 호출
   - "잔고 절반으로 비트코인 사줘" -> 1) get_account_balances로 원화 잔고 확인 -> 2) get_ticker_price로 시세 확인 -> 3) 금액/수량 계산 후 propose_manual_order 호출
   - "DCA/전략 일시중지해줘" -> 1) get_strategy_templates로 ID 확인 -> 2) propose_template_action 호출
   - "이번 달 손익이랑 승률 어때?" -> 1) get_report_pnl(period="30d") -> 2) get_report_win_stats(period="30d") 호출 후 종합 요약
3. 매매 주문, 주문 취소, 전략 실행, 설정 변경 등 실제 계좌나 DB에 변경을 주는 행위는 즉시 실행되지 않으며, propose_* 도구를 통해 제안됩니다. 제안 후 사용자에게 확인 버튼이 표시되므로, 최종 응답에서는 제안한 계획의 핵심 요약을 친절하고 명확하게 한국어로 브리핑하세요.
4. 존댓말과 전문적이고 명확한 한국어 톤을 유지하세요. 마크다운을 적절히 활용하여 가독성을 높이세요.
"""


@dataclass
class AgentRunResult:
    reply_text: str
    proposed_actions: list[dict] = field(default_factory=list)
    tool_trace: list[dict] = field(default_factory=list)


# 도구 이름 매핑
_TOOL_MAP = {func.__name__: func for func in ALL_NL_TOOLS}


async def _execute_tool_call(tool_name: str, tool_args: dict, ctx: NLToolContext) -> dict:
    func = _TOOL_MAP.get(tool_name)
    if not func:
        return {"error": f"알 수 없는 도구입니다: {tool_name}"}

    try:
        if inspect.iscoroutinefunction(func):
            res = await func(**tool_args)
        else:
            res = func(**tool_args)
        return res
    except Exception as e:
        _log.warning("Tool execution error: tool=%s, args=%s, err=%s", tool_name, tool_args, e)
        return {"error": f"도구 실행 중 오류가 발생했습니다: {str(e)}"}


async def run_nl_agent_loop(
    text: str,
    user: dict,
    user_id: str,
    recent_context: Optional[list[dict]] = None,
    exchange_adapter: Any = None,
    order_manager: Any = None,
    signal_engine: Any = None,
    user_manager: Any = None,
    max_steps: int = MAX_AGENT_STEPS,
) -> AgentRunResult:
    """Gemini Function Calling 멀티턴 에이전트 루프를 실행한다."""
    api_key = user.get("llm", {}).get("gemini_api_key", "").strip()
    if not api_key:
        return AgentRunResult(
            reply_text="⚠️ Gemini API 키가 설정되지 않았습니다. /config 명령어로 키를 등록해 주세요.",
            proposed_actions=[],
            tool_trace=[],
        )

    from google import genai
    from google.genai import types

    ctx = NLToolContext(
        user=user,
        user_id=str(user_id),
        exchange_adapter=exchange_adapter,
        order_manager=order_manager,
        signal_engine=signal_engine,
        user_manager=user_manager,
    )
    token = current_nl_context.set(ctx)

    try:
        client = genai.Client(api_key=api_key)
        model_name = user.get("preferences", {}).get("llm_model", "gemini-2.5-flash-lite")

        # 최근 대화 문맥을 시스템 프롬프트 뒤에 보강
        sys_instruction = SYSTEM_INSTRUCTION
        if recent_context and isinstance(recent_context, list):
            context_lines = []
            for item in recent_context:
                role = item.get("role", "user")
                if role == "user":
                    context_lines.append(f"User: {item.get('text', '')}")
                elif role == "bot":
                    act = item.get("action")
                    summary = item.get("summary") or item.get("ticker")
                    context_lines.append(f"Bot resolved: {act} ({summary})")
            if context_lines:
                sys_instruction += f"\n\n[최근 대화 맥락]\n" + "\n".join(context_lines)

        config = types.GenerateContentConfig(
            system_instruction=sys_instruction,
            temperature=0.1,
            tools=ALL_NL_TOOLS,
        )

        contents = [types.Content(role="user", parts=[types.Part.from_text(text=text)])]
        step = 0
        final_reply = ""

        while step < max_steps:
            step += 1

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=contents,
                config=config,
            )

            if not response.candidates:
                final_reply = "⚠️ AI 응답을 생성하지 못했습니다."
                break

            candidate = response.candidates[0]
            model_content = candidate.content
            contents.append(model_content)

            # Function calls 추출
            function_calls = []
            if model_content and model_content.parts:
                for part in model_content.parts:
                    if part.function_call:
                        function_calls.append(part.function_call)

            if not function_calls:
                # 텍스트 응답 추출 후 루프 종료
                final_reply = response.text or ""
                break

            # Function Calls 병렬/순차 실행
            tool_response_parts = []
            for fc in function_calls:
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}

                tool_result = await _execute_tool_call(fn_name, fn_args, ctx)
                ctx.call_trace.append({
                    "step": step,
                    "tool": fn_name,
                    "args": fn_args,
                    "result": tool_result,
                })

                # Gemini Part 형식으로 결과 래핑
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": tool_result},
                    )
                )

            # 실행 결과를 모델 컨텍스트에 추가
            contents.append(types.Content(role="tool", parts=tool_response_parts))

        if step >= max_steps and not final_reply:
            final_reply = "요청을 처리하는 도중 최대 단계(5회)에 도달했습니다. 더 구체적인 요청으로 나누어 질문해 주세요."

        return AgentRunResult(
            reply_text=final_reply.strip(),
            proposed_actions=list(ctx.proposed_actions),
            tool_trace=list(ctx.call_trace),
        )
    except Exception as e:
        _log.error("run_nl_agent_loop error: %s", e, exc_info=True)
        return AgentRunResult(
            reply_text=f"⚠️ AI 요청 처리 중 오류가 발생했습니다: {str(e)}",
            proposed_actions=[],
            tool_trace=list(ctx.call_trace),
        )
    finally:
        current_nl_context.reset(token)
