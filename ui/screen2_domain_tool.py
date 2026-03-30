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


def _load_tools(filename: str) -> list[dict] | None:
    path = os.path.join(_TOOLS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tools", [])


def _build_card_html(domain: dict, selected_key: str | None) -> str:
    is_selected = selected_key == domain["key"]
    card_class = "card selected" if is_selected else "card"

    examples_html = "".join(
        f'<div class="card-tool">⚙ {t}</div>' for t in domain["tool_examples"]
    )

    return f"""
    <div class="{card_class}" id="card-{domain['key']}" onclick="selectCard('{domain['key']}')">
        <div class="card-badge">{domain["badge"]}</div>
        <div class="card-title">{domain["label"]}</div>
        <div class="card-desc">{domain["desc"]}</div>
        <div class="card-tools-label">기본 Tool 예시</div>
        {examples_html}
    </div>
    """


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
        st.session_state["domain_draft"] = chosen
        st.rerun()

    # --- 선택된 도메인의 Tool 목록 ---
    confirmed: str | None = st.session_state.get("domain_draft")
    if confirmed:
        domain_meta = next(d for d in DOMAINS if d["key"] == confirmed)
        st.divider()
        st.subheader(f"[{domain_meta['badge']}] {domain_meta['label']} — 등록된 Tool 목록")

        tools = _load_tools(domain_meta["file"])
        if tools is None:
            st.info("이 도메인은 현재 준비 중입니다. 곧 Tool 데이터가 추가될 예정입니다.")
        elif len(tools) == 0:
            st.warning("Tool 파일은 있지만 등록된 Tool이 없습니다.")
        else:
            st.caption(f"총 {len(tools)}개의 Tool이 등록되어 있습니다.")
            _render_tool_table(tools)

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
