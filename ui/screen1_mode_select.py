import streamlit as st
import streamlit.components.v1 as components


MODES = [
    {
        "key": "knowledge",
        "label": "도메인 지식 평가",
        "desc": (
            "이 LLM이 우리 회사 업무를 얼마나 잘 알고 있는지 확인합니다. "
            "금융·법률·HR 등 도메인 전문 지식과 답변 품질을 점수로 보여줍니다."
        ),
        "metrics": [
            "사실 정확도",
            "한국어 자연성",
            "잘못된 정보 생성 여부",
            "도메인 전문성",
            "응답 적절성",
        ],
        "judge": "채점 방식: 외부 AI 자동 채점 + 담당자 검토",
        "badge": None,
    },
    {
        "key": "agent",
        "label": "업무 자동화 능력 평가",
        "desc": (
            "이 LLM이 실제 업무 시스템을 올바르게 사용할 수 있는지 확인합니다. "
            "ERP, CRM 같은 사내 도구를 LLM이 제대로 호출하는지 테스트합니다."
        ),
        "metrics": [
            "도구 호출 정확도",
            "정보 부족 시 적절한 질문",
            "불가능한 요청 적절히 거절",
            "결과 요약 품질",
        ],
        "judge": "채점 방식: 외부 AI 자동 채점 + 담당자 검토",
        "badge": None,
    },
    {
        "key": "integrated",
        "label": "종합 평가 (추천)",
        "desc": (
            "지식 평가와 업무 수행 능력을 함께 측정합니다. "
            "두 점수를 한눈에 비교해서 어떤 LLM이 우리 회사에 가장 잘 맞는지 파악할 수 있습니다."
        ),
        "metrics": [
            "도메인 지식 전 항목",
            "업무 자동화 전 항목",
            "지식 vs 업무 수행 비교 매트릭스",
        ],
        "judge": "채점 방식: 외부 AI 자동 채점 + 담당자 검토",
        "badge": "추천",
    },
]


def _build_card_html(mode: dict, selected_key: str | None) -> str:
    is_selected = selected_key == mode["key"]
    card_class = "card selected" if is_selected else "card"

    badge_html = ""
    if mode["badge"]:
        badge_html = f'<div class="card-badge">★ {mode["badge"]}</div>'

    metrics_html = "".join(
        f'<div class="card-metric">✓ {m}</div>' for m in mode["metrics"]
    )

    return f"""
    <div class="{card_class}" id="card-{mode['key']}" onclick="selectCard('{mode['key']}')">
        {badge_html}
        <div class="card-title">{mode["label"]}</div>
        <div class="card-desc">{mode["desc"]}</div>
        <div class="card-metrics-label">평가 항목</div>
        {metrics_html}
        <div class="card-judge">{mode["judge"]}</div>
    </div>
    """


def render() -> None:
    st.title("BenchMate")
    st.write("평가하려는 목적에 맞는 모드를 선택하세요.")

    selected: str | None = st.session_state.get("eval_mode_draft")

    # 카드 HTML 조각 생성
    all_cards = "".join(_build_card_html(m, selected) for m in MODES)

    # components.v1.html()로 완전한 HTML/CSS/JS를 iframe 안에서 렌더링
    components.html(
        f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: transparent; padding: 4px 0; }}
  .cards-container {{ display: flex; gap: 1.25rem; }}
  .card {{
    flex: 1;
    border: 1.5px solid #e0e0e0;
    border-radius: 12px;
    padding: 1.4rem;
    background: #ffffff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
    user-select: none;
  }}
  .card:hover {{
    border-color: #a0c0ff;
    box-shadow: 0 2px 8px rgba(79,142,247,0.12);
  }}
  .card.selected {{
    border-color: #4F8EF7;
    box-shadow: 0 0 0 2.5px #4F8EF7, 0 2px 10px rgba(79,142,247,0.18);
    background: #f5f8ff;
  }}
  .card-badge {{
    display: inline-block;
    background: #4F8EF7;
    color: #fff;
    font-size: 0.7rem;
    font-weight: 700;
    border-radius: 20px;
    padding: 2px 10px;
    margin-bottom: 0.65rem;
    letter-spacing: 0.04em;
  }}
  .card-title {{
    font-size: 1.05rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    color: #1a1a2e;
  }}
  .card-desc {{
    font-size: 0.84rem;
    color: #555;
    line-height: 1.65;
    margin-bottom: 0.9rem;
  }}
  .card-metrics-label {{
    font-size: 0.73rem;
    font-weight: 700;
    color: #333;
    margin-bottom: 0.3rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .card-metric {{
    font-size: 0.8rem;
    color: #444;
    padding: 2px 0;
  }}
  .card-judge {{
    font-size: 0.72rem;
    color: #999;
    margin-top: 0.85rem;
    padding-top: 0.65rem;
    border-top: 1px solid #ebebeb;
  }}
</style>
</head>
<body>
  <div class="cards-container">
    {all_cards}
  </div>

  <script>
    // 카드 클릭 시 iframe 내부 시각적 선택 상태 관리
    function selectCard(key) {{
      document.querySelectorAll('.card').forEach(function(c) {{
        c.classList.remove('selected');
      }});
      var target = document.getElementById('card-' + key);
      if (target) target.classList.add('selected');

      // 부모 Streamlit 페이지의 숨겨진 radio 버튼을 클릭해 session_state 동기화
      try {{
        var keys = {[m['key'] for m in MODES]};
        var idx = keys.indexOf(key);
        var radios = window.parent.document.querySelectorAll('input[type="radio"]');
        if (radios[idx]) {{
          radios[idx].click();
        }}
      }} catch(e) {{}}
    }}
  </script>
</body>
</html>""",
        height=490,
        scrolling=False,
    )

    # 숨겨진 radio — session_state 저장용 (CSS로 비표시)
    st.markdown(
        "<style>div[data-testid='stRadio']{display:none!important;}</style>",
        unsafe_allow_html=True,
    )
    mode_keys = [m["key"] for m in MODES]
    default_idx = mode_keys.index(selected) if selected in mode_keys else 0
    chosen = st.radio(
        "eval_mode_draft",
        options=mode_keys,
        index=default_idx,
        label_visibility="collapsed",
        key="_mode_radio",
    )
    # radio 변경 시 session_state 동기화
    if chosen != selected:
        st.session_state["eval_mode_draft"] = chosen
        st.rerun()

    st.divider()

    confirmed = st.session_state.get("eval_mode_draft")
    if confirmed is None:
        st.caption("모드를 선택하면 다음 단계로 이동할 수 있습니다.")
    else:
        mode_label = next(m["label"] for m in MODES if m["key"] == confirmed)
        st.write(f"**{mode_label}** 선택 완료")

    if st.button("다음 →", disabled=confirmed is None, type="primary"):
        st.session_state["eval_mode"] = confirmed
        st.session_state["current_screen"] = 2
        st.rerun()
