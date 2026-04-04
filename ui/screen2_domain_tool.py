import json
import os
import streamlit as st
import streamlit.components.v1 as components


DOMAINS = [
    {
        "key": "finance",
        "label": "금융",
        "badge": "FIN",
        "desc": "대출·금리·투자 등 금융 실무 지식과 내부 시스템 연동 능력을 평가합니다.",
        "tool_examples": ["search_loan_rate", "calculate_interest", "get_account_balance"],
        "file": "finance_tools.json",
    },
    {
        "key": "legal",
        "label": "법률·규정",
        "badge": "LAW",
        "desc": "계약서 검토, 컴플라이언스 조회, 규정 해석 등 법률 실무 능력을 평가합니다.",
        "tool_examples": ["search_regulation", "check_compliance", "lookup_contract_clause"],
        "file": "legal_tools.json",
    },
    {
        "key": "hr",
        "label": "인사·HR",
        "badge": "HR",
        "desc": "채용, 급여, 복리후생, 인사 규정 등 HR 실무 지식과 시스템 연동 능력을 평가합니다.",
        "tool_examples": ["get_employee_info", "calculate_salary", "check_leave_balance"],
        "file": "hr_tools.json",
    },
    {
        "key": "cs",
        "label": "고객응대·CS",
        "badge": "CS",
        "desc": "고객 문의 응답, 불만 처리, 주문·배송 조회 등 CS 실무 능력을 평가합니다.",
        "tool_examples": ["lookup_order_status", "process_refund_request", "search_faq"],
        "file": "cs_tools.json",
    },
    {
        "key": "manufacturing",
        "label": "제조·기술문서",
        "badge": "MFG",
        "desc": "설비 매뉴얼 해석, 불량 분석, 공정 파라미터 조회 등 제조 실무 능력을 평가합니다.",
        "tool_examples": ["search_equipment_manual", "get_process_parameter", "lookup_defect_code"],
        "file": "manufacturing_tools.json",
    },
]

_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "tools")

_AVAILABLE_DOMAINS = {"finance"}


def _load_tools(filename: str) -> list[dict] | None:
    path = os.path.join(_TOOLS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tools", [])


def _build_card_html(domain: dict, selected_key: str | None) -> str:
    is_available = domain["key"] in _AVAILABLE_DOMAINS
    is_selected = selected_key == domain["key"]

    if is_available:
        card_class = "card selected" if is_selected else "card"
        onclick = f"onclick=\"selectCard('{domain['key']}')\""
        coming_soon_badge = ""
    else:
        card_class = "card disabled"
        onclick = ""
        coming_soon_badge = '<div class="card-coming-soon">준비 중</div>'

    examples_html = "".join(
        f'<div class="card-tool">⚙ {t}</div>' for t in domain["tool_examples"]
    )

    return f"""
    <div class="{card_class}" id="card-{domain['key']}" {onclick}>
        {coming_soon_badge}
        <div class="card-badge">{domain["badge"]}</div>
        <div class="card-title">{domain["label"]}</div>
        <div class="card-desc">{domain["desc"]}</div>
        <div class="card-tools-label">기본 Tool 예시</div>
        {examples_html}
    </div>
    """


_TOOL_EXAMPLE = {
    "name": "customer_credit_check",
    "description": "고객 ID를 입력받아 신용등급과 대출 가능 여부를 조회합니다.",
    "inputs": "고객ID(필수), 조회일자(선택)",
    "outputs": "신용등급(1~10등급), 대출가능여부, 한도금액",
}


def _render_custom_tool_form() -> None:
    # 폼 draft 상태 초기화
    st.session_state.setdefault("tool_name_draft", "")
    st.session_state.setdefault("tool_desc_draft", "")
    st.session_state.setdefault("tool_inputs_draft", "")
    st.session_state.setdefault("tool_outputs_draft", "")

    with st.expander("+ 사내 기능 직접 추가", expanded=False):
        # 예시 채우기 버튼
        _, col_btn = st.columns([5, 1])
        with col_btn:
            if st.button("예시 채우기 →", key="btn_tool_example"):
                st.session_state["tool_name_draft"] = _TOOL_EXAMPLE["name"]
                st.session_state["tool_desc_draft"] = _TOOL_EXAMPLE["description"]
                st.session_state["tool_inputs_draft"] = _TOOL_EXAMPLE["inputs"]
                st.session_state["tool_outputs_draft"] = _TOOL_EXAMPLE["outputs"]
                st.rerun()

        name = st.text_input(
            "기능명 *",
            value=st.session_state["tool_name_draft"],
            placeholder="예: 고객 신용등급 조회",
        )
        st.session_state["tool_name_draft"] = name

        description = st.text_input(
            "설명",
            value=st.session_state["tool_desc_draft"],
            placeholder="예: 고객 ID를 입력하면 신용등급과 연체 이력을 반환합니다.",
        )
        st.session_state["tool_desc_draft"] = description

        inputs = st.text_area(
            "입력값",
            value=st.session_state["tool_inputs_draft"],
            placeholder="예: 고객ID(필수), 조회일자(선택)",
            height=80,
        )
        st.session_state["tool_inputs_draft"] = inputs

        outputs = st.text_area(
            "출력값",
            value=st.session_state["tool_outputs_draft"],
            placeholder="예: 신용등급, 연체이력",
            height=80,
        )
        st.session_state["tool_outputs_draft"] = outputs

        if st.button("추가", type="primary", use_container_width=True, key="add_custom_tool"):
            if not name.strip():
                st.error("기능명을 입력하세요.")
            else:
                new_tool = {
                    "name": name.strip(),
                    "description": description.strip(),
                    "parameters": [
                        {
                            "name": "input",
                            "type": "string",
                            "required": True,
                            "description": inputs.strip(),
                        }
                    ],
                    "mock_return": {"result": outputs.strip() or "사용자 정의 Tool 결과"},
                }
                tools = st.session_state.get("available_tools", [])
                tools.append(new_tool)
                st.session_state["available_tools"] = tools
                # draft 초기화
                st.session_state["tool_name_draft"] = ""
                st.session_state["tool_desc_draft"] = ""
                st.session_state["tool_inputs_draft"] = ""
                st.session_state["tool_outputs_draft"] = ""
                st.success(f"'{name.strip()}' 기능이 추가됐습니다.")
                st.rerun()

    custom_tools: list[dict] = st.session_state.get("available_tools", [])
    if custom_tools:
        st.markdown(f"**직접 추가한 기능 ({len(custom_tools)}개)**")
        for t in custom_tools:
            with st.expander(f"**{t['name']}**  —  {t.get('description', '')}", expanded=False):
                params = t.get("parameters", [])
                if params and params[0].get("description"):
                    st.markdown(f"**입력값:** {params[0]['description']}")
                result = t.get("mock_return", {}).get("result", "")
                if result and result != "사용자 정의 Tool 결과":
                    st.markdown(f"**출력값:** {result}")
        if st.button("추가 기능 전체 삭제", key="clear_custom_tools"):
            st.session_state["available_tools"] = []
            st.rerun()


def _render_tool_table(tools: list[dict]) -> None:
    for tool in tools:
        params = tool.get("parameters", [])
        required_params = [p["name"] for p in params if p.get("required")]
        optional_params = [p["name"] for p in params if not p.get("required")]

        with st.expander(f"**{tool['name']}**  —  {tool.get('description', '')}", expanded=False):
            if required_params:
                st.markdown(
                    "**필수 파라미터:** " + ", ".join(f"`{p}`" for p in required_params)
                )
            if optional_params:
                st.markdown(
                    "**선택 파라미터:** " + ", ".join(f"`{p}`" for p in optional_params)
                )
            if params:
                rows = [
                    f"| `{p['name']}` | {p['type']} | {'✓' if p.get('required') else ''} | {p.get('description', '')} |"
                    for p in params
                ]
                st.markdown(
                    "| 파라미터 | 타입 | 필수 | 설명 |\n|---|---|---|---|\n" + "\n".join(rows)
                )


def render() -> None:
    st.title("BenchMate")
    st.write("평가할 업무 도메인을 선택하세요.")

    st.caption("LLM이 사내 시스템(고객 조회, 금리 계산 등)을 직접 사용하는 능력도 평가합니다.")
    with st.expander("사내 시스템 연동 기능이란?  자세히 보기 →", expanded=False):
        st.markdown(
            """LLM은 단순히 질문에 답하는 것을 넘어, 실제 사내 시스템을 직접 조작할 수 있습니다.

예를 들어 직원이 **'홍길동 고객의 대출 금리 조회해줘'** 라고 말하면
LLM이 고객 관리 시스템에서 데이터를 직접 가져와 답변합니다.

**BenchMate**는 LLM이 이런 사내 시스템 기능을 정확하게 사용할 수 있는지도 함께 평가합니다."""
        )

    selected: str | None = st.session_state.get("domain_draft")

    all_cards = "".join(_build_card_html(d, selected) for d in DOMAINS)
    domain_keys = [d["key"] for d in DOMAINS]

    components.html(
        f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: transparent; padding: 4px 0; }}
  .cards-container {{ display: flex; gap: 1rem; }}
  .card {{
    flex: 1;
    border: 1.5px solid #e0e0e0;
    border-radius: 12px;
    padding: 1.2rem;
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
    background: #2563EB;
    color: #fff;
    font-size: 0.65rem;
    font-weight: 700;
    border-radius: 5px;
    padding: 2px 7px;
    margin-bottom: 0.55rem;
    letter-spacing: 0.06em;
  }}
  .card-title {{
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 0.45rem;
    color: #1a1a2e;
  }}
  .card-desc {{
    font-size: 0.78rem;
    color: #555;
    line-height: 1.6;
    margin-bottom: 0.85rem;
  }}
  .card-tools-label {{
    font-size: 0.7rem;
    font-weight: 700;
    color: #333;
    margin-bottom: 0.25rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .card-tool {{
    font-size: 0.75rem;
    color: #666;
    padding: 1px 0;
    font-family: "SFMono-Regular", Consolas, monospace;
  }}
  .card.disabled {{
    position: relative;
    background: #f5f5f5;
    border-color: #e0e0e0;
    cursor: not-allowed;
    opacity: 0.65;
  }}
  .card.disabled:hover {{
    border-color: #e0e0e0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }}
  .card.disabled .card-badge {{
    background: #9ca3af;
  }}
  .card.disabled .card-title,
  .card.disabled .card-desc,
  .card.disabled .card-tools-label,
  .card.disabled .card-tool {{
    color: #aaa;
  }}
  .card-coming-soon {{
    position: absolute;
    top: 0.6rem;
    right: 0.6rem;
    background: #9ca3af;
    color: #fff;
    font-size: 0.6rem;
    font-weight: 700;
    border-radius: 4px;
    padding: 2px 6px;
    letter-spacing: 0.04em;
  }}
</style>
</head>
<body>
  <div class="cards-container">
    {all_cards}
  </div>

  <script>
    function selectCard(key) {{
      document.querySelectorAll('.card').forEach(function(c) {{
        c.classList.remove('selected');
      }});
      var target = document.getElementById('card-' + key);
      if (target) target.classList.add('selected');

      try {{
        var keys = {domain_keys};
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
        height=330,
        scrolling=False,
    )

    st.caption("※ 금융 외 도메인은 사내 문서 업로드 기능 출시 후 이용 가능합니다.")

    # 숨겨진 radio — session_state 저장용
    st.markdown(
        "<style>div[data-testid='stRadio'] { display: none !important; }</style>",
        unsafe_allow_html=True,
    )
    default_idx = domain_keys.index(selected) if selected in domain_keys else None
    chosen = st.radio(
        "domain_draft",
        options=domain_keys,
        index=default_idx,
        label_visibility="collapsed",
        key="_domain_radio",
    )
    if chosen != selected:
        if chosen in _AVAILABLE_DOMAINS:
            st.session_state["domain_draft"] = chosen
        st.rerun()

    # --- 선택된 도메인의 Tool 목록 ---
    confirmed: str | None = st.session_state.get("domain_draft")
    if confirmed:
        domain_meta = next(d for d in DOMAINS if d["key"] == confirmed)
        st.divider()
        st.subheader(f"[{domain_meta['badge']}] {domain_meta['label']} — 등록된 Tool 목록")

        st.info(
            "아래는 해당 도메인에서 자주 사용하는 사내 시스템 기능 예시입니다.\n\n"
            "✅ **우리 회사에서 실제로 사용하는 기능이 있다면 추가해주세요.**\n"
            "예: 사내 CRM에서 고객 정보를 조회하는 기능, ERP에서 재고를 확인하는 기능 등\n\n"
            "✅ **시스템이 외부에 공개되지 않았거나 자체 구축한 경우에도 괜찮습니다.**\n"
            "기능 이름과 '어떤 정보를 입력하면 어떤 결과가 나오는지'만 알려주시면 "
            "BenchMate가 평가용 시나리오를 자동으로 만들어드립니다.\n\n"
            "작성 예시\n"
            "- 기능명: 고객 신용등급 조회\n"
            "- 입력값: 고객 ID, 조회 일자\n"
            "- 출력값: 신용등급(1~10등급), 연체 이력 여부"
        )

        tools = _load_tools(domain_meta["file"])
        if tools is None:
            st.info("이 도메인은 현재 준비 중입니다. 곧 기능 데이터가 추가될 예정입니다.")
        elif len(tools) == 0:
            st.warning("기능 파일은 있지만 등록된 기능이 없습니다.")
        else:
            st.caption(f"총 {len(tools)}개의 기능이 등록되어 있습니다.")
            _render_tool_table(tools)

        _render_custom_tool_form()

    st.divider()

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("← 이전", use_container_width=True):
            st.session_state["current_screen"] = 1
            st.rerun()
    with col_next:
        if st.button(
            "다음 →",
            disabled=confirmed is None,
            type="primary",
            use_container_width=True,
        ):
            st.session_state["domain"] = confirmed
            st.session_state["current_screen"] = 3
            st.rerun()
