"""
HuggingFace Inference API 오류 → 사용자 친화적 메시지 변환 유틸리티.
judge_knowledge, judge_agent, generate_report 노드에서 공유한다.
"""

from __future__ import annotations


class JudgeError(RuntimeError):
    """Judge 모델(HuggingFace) 호출 실패를 나타내는 예외."""
    pass


def _extract_status_code(exc: Exception) -> int | None:
    """예외에서 HTTP 상태 코드를 추출한다."""
    # huggingface_hub.utils.HfHubHTTPError는 response 속성을 가진다
    response = getattr(exc, "response", None)
    if response is not None and hasattr(response, "status_code"):
        return int(response.status_code)

    # 메시지 문자열에서 상태 코드 감지 (폴백)
    msg = str(exc)
    for code in (401, 402, 503):
        if str(code) in msg:
            return code

    return None


def translate_hf_error(exc: Exception) -> JudgeError | None:
    """
    HuggingFace HTTP 오류를 JudgeError로 변환한다.
    알려진 오류 코드가 아니면 None을 반환한다.
    """
    status = _extract_status_code(exc)

    if status == 402:
        return JudgeError(
            "Judge 모델(HuggingFace) 크레딧이 소진됐습니다. "
            "https://huggingface.co/settings/billing 에서 충전 후 다시 시도해주세요."
        )
    if status == 401:
        return JudgeError(
            "HuggingFace 토큰이 유효하지 않습니다. .env의 HF_TOKEN을 확인해주세요."
        )
    if status == 503:
        return JudgeError(
            "Judge 모델 서버가 일시적으로 과부하 상태입니다. 잠시 후 다시 시도해주세요."
        )

    return None
