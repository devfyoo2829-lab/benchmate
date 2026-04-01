"""
BenchMate — Screen 7: PM 해석 리포트 + 내보내기
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from ui.charts import (
    MODEL_DISPLAY_NAMES,
    KNOWLEDGE_KEYS,
    KNOWLEDGE_AXES,
    AGENT_ITEMS,
    AGENT_LABELS,
    extract_model_stats,
    has_knowledge_data,
    has_agent_data,
    build_scatter_fig,
    build_knowledge_bar_fig,
    build_radar_fig,
    build_agent_bar_fig,
    fig_to_png,
)

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "output"

DOMAIN_NAMES: dict[str, str] = {
    "finance": "금융",
    "legal": "법무",
    "hr": "인사",
    "cs": "고객서비스",
    "manufacturing": "제조",
}


# ── 추천 모델 선택 ──────────────────────────────────────────────────────────────

def _get_best_model(summary_table: dict) -> str:
    best_model = ""
    best_score: float = -1.0
    for model, sections in summary_table.items():
        total = (sections.get("knowledge") or {}).get("total")
        if total is not None and total > best_score:
            best_score = total
            best_model = model
    return best_model or "—"


# ── 세션 JSON 파일 경로 탐색 ───────────────────────────────────────────────────

def _find_session_json(eval_result: dict) -> Path | None:
    session_id: str = eval_result.get("eval_session_id", "")
    if not session_id:
        return None
    path = _OUTPUT_DIR / f"{session_id}.json"
    return path if path.exists() else None


# ── pm_report_text 섹션 파싱 ──────────────────────────────────────────────────

def _extract_section(report_text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, report_text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_bullets(report_text: str, heading: str) -> list[str]:
    """섹션에서 불릿 항목을 추출한다. 최대 3개, 마크다운 볼드 제거."""
    section = _extract_section(report_text, heading)
    bullets = re.findall(r"^[-*]\s+(.+)", section, re.MULTILINE)
    clean = [re.sub(r"\*\*(.+?)\*\*", r"\1", b).strip() for b in bullets[:3]]
    return clean


def _extract_ai_analysis(report_text: str) -> str:
    skip = {"평가 개요", "점수 비교", "비용 분석", "추천 모델", "모델별 점수 요약", "강점 분석", "리스크 & 권고"}
    lines = report_text.splitlines()
    result: list[str] = []
    skip_current = False
    for line in lines:
        if line.startswith("## "):
            heading = re.sub(r"^##\s+\d+\.\s*", "", line[3:]).strip()
            skip_current = any(k in heading for k in skip)
        if not skip_current:
            result.append(line)
    return "\n".join(result).strip()


# ── McKinsey 스타일 1장 PDF ────────────────────────────────────────────────────

def _build_mckinsey_pdf(
    eval_result: dict,
    model_stats: dict[str, dict],
    report_text: str,
) -> bytes | None:
    """1페이지 컨설팅 스타일 PDF (블랙톤).

    헤더 → KPI 4개 → 핵심발견 → 모델 비교 표 → 강점/리스크 → 차트 2개 → 푸터
    각 섹션은 독립적으로 try/except로 보호된다.
    """
    import importlib.util
    import os
    import tempfile

    # ── reportlab 임포트 ──────────────────────────────────────────────────────
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import (
            HRFlowable, Image, Paragraph,
            SimpleDocTemplate, Spacer, Table, TableStyle,
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError as e:
        st.warning(f"PDF 생성 실패: reportlab 미설치 — {e}\n`.venv/bin/pip install reportlab` 으로 설치하세요.")
        return None

    # ── 색상 시스템 — 블랙톤 + 강조색 2가지 ──────────────────────────────────
    BLACK        = colors.HexColor("#1A1A1A")
    DARK_GRAY    = colors.HexColor("#4A4A4A")
    MEDIUM_GRAY  = colors.HexColor("#888888")
    LIGHT_GRAY   = colors.HexColor("#F5F5F5")
    BORDER_GRAY  = colors.HexColor("#DDDDDD")
    ACCENT_BLUE  = colors.HexColor("#2563EB")   # 헤더·추천 모델 배경
    ACCENT_AMBER = colors.HexColor("#F59E0B")   # 최고값 셀
    CELL_BEST    = colors.HexColor("#FEF3C7")   # Amber-100
    CELL_DANGER  = colors.HexColor("#FEE2E2")   # Red-100 (허위정보 ≤2)
    WHITE        = colors.white

    # 순위별 바 색상
    _RANK_COLORS = ["#1A1A1A", "#2563EB", "#93C5FD", "#93C5FD", "#93C5FD"]
    _CHART_COLORS = ["#2563EB", "#F59E0B", "#4FD1C5", "#F7844F", "#A78BFA"]

    # USD → KRW
    USD_TO_KRW = 1_380

    # ── 한글 폰트 등록 ────────────────────────────────────────────────────────
    _FN      = "Helvetica"
    _FN_BOLD = "Helvetica-Bold"

    _NANUM_R  = str(Path.home() / "Library/Fonts/NanumBarunGothic.ttf")
    _NANUM_B  = str(Path.home() / "Library/Fonts/NanumBarunGothicBold.ttf")
    _TTC_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

    if Path(_NANUM_R).exists():
        try:
            pdfmetrics.registerFont(TTFont("NanumBarunGothic", _NANUM_R))
            _FN = "NanumBarunGothic"
        except Exception:
            pass
    if Path(_NANUM_B).exists():
        try:
            pdfmetrics.registerFont(TTFont("NanumBarunGothicBold", _NANUM_B))
            _FN_BOLD = "NanumBarunGothicBold"
        except Exception:
            pass
    if _FN == "Helvetica" and Path(_TTC_PATH).exists():
        for idx in (0, 1, 2):
            try:
                pdfmetrics.registerFont(TTFont("KorFont", _TTC_PATH, subfontIndex=idx))
                _FN = _FN_BOLD = "KorFont"
                break
            except Exception:
                pass
    if _FN == "Helvetica":
        st.warning("한글 폰트를 찾지 못했습니다 — PDF 텍스트가 깨질 수 있습니다.")

    # ── 스타일 팩토리 ─────────────────────────────────────────────────────────
    def _st(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, fontName=_FN, **kw)

    def _stb(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, fontName=_FN_BOLD, **kw)

    # 헤더
    s_logo    = _stb("logo",    fontSize=14, leading=18, textColor=BLACK)
    s_docinfo = _st("docinfo",  fontSize=7,  leading=10, textColor=DARK_GRAY)

    # KPI — 추천 모델 박스 (ACCENT_BLUE bg / 흰 글자)
    s_kpi_lbl_w = _st("kpilbl_w",  fontSize=7,  leading=10, textColor=WHITE,       alignment=1)
    s_kpi_val_w = _stb("kpival_w", fontSize=14, leading=18, textColor=WHITE,       alignment=1)
    s_kpi_sub_w = _st("kpisub_w",  fontSize=7,  leading=10, textColor=colors.HexColor("#BFDBFE"), alignment=1)

    # KPI — 나머지 박스
    s_kpi_lbl = _st("kpilbl",  fontSize=7,  leading=10, textColor=DARK_GRAY,  alignment=1)
    s_kpi_val = _stb("kpival", fontSize=14, leading=18, textColor=BLACK,      alignment=1)
    s_kpi_sub = _st("kpisub",  fontSize=7,  leading=10, textColor=MEDIUM_GRAY, alignment=1)

    # 섹션 헤더
    s_sec_hd   = _stb("sechd",   fontSize=8, leading=11, textColor=BLACK)
    s_sec_hd_w = _stb("sechd_w", fontSize=8, leading=11, textColor=WHITE)

    # 표 — 헤더 7.5pt 볼드 흰색 / 본문 7.5pt
    s_th    = _stb("th",   fontSize=7.5, leading=10, textColor=WHITE,      alignment=1)
    s_td    = _st("td",    fontSize=7.5, leading=10, textColor=DARK_GRAY)
    s_td_c  = _st("tdc",   fontSize=7.5, leading=10, textColor=DARK_GRAY,  alignment=1)
    s_td_hi = _stb("tdhi", fontSize=7.5, leading=10, textColor=BLACK)
    s_td_hic= _stb("tdhic",fontSize=7.5, leading=10, textColor=BLACK,      alignment=1)

    # 기타
    s_insight  = _st("insight",  fontSize=7.5, leading=10, textColor=DARK_GRAY)
    s_bullet   = _st("bullet",   fontSize=7.5, leading=9,  textColor=DARK_GRAY, leftIndent=6)
    s_caption  = _st("caption",  fontSize=6.5, leading=9,  textColor=MEDIUM_GRAY, alignment=1)
    s_footer   = _st("footer",   fontSize=6,   leading=9,  textColor=MEDIUM_GRAY, alignment=1)
    s_legend   = _st("legend",   fontSize=6.5, leading=9,  textColor=MEDIUM_GRAY)
    s_footnote = _st("footnote", fontSize=6.5, leading=9,  textColor=MEDIUM_GRAY)

    # ── 문서 설정 — A4, 상10mm 하8mm 좌우12mm ────────────────────────────────
    buf = io.BytesIO()
    page_w, _ = A4
    MM = 2.8346
    L_MAR = R_MAR = round(12 * MM)   # ≈ 34 pt
    T_MAR         = round(10 * MM)   # ≈ 28 pt
    B_MAR         = round(8  * MM)   # ≈ 23 pt
    content_w = page_w - L_MAR - R_MAR  # ≈ 527 pt

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=L_MAR, rightMargin=R_MAR,
        topMargin=T_MAR, bottomMargin=B_MAR,
    )
    elems: list = []

    # ── 공유 변수 ─────────────────────────────────────────────────────────────
    summary_table_data: dict = eval_result.get("summary_table") or {}
    cost_dict: dict = eval_result.get("estimated_cost") or {}
    has_k: bool = has_knowledge_data(model_stats)
    has_a: bool = has_agent_data(
        model_stats, eval_result, st.session_state.get("eval_mode", "")
    )
    date_str_kst = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")

    # best_model: 1) knowledge total → 2) agent call_score → 3) selected_models[0]
    best_model = _get_best_model(summary_table_data)
    if not best_model or best_model == "—":
        _best_call = -1.0
        for _m, _d in model_stats.items():
            _cs = _d.get("agent_scores", {}).get("call", 0.0)
            if isinstance(_cs, (int, float)) and _cs > _best_call:
                _best_call = _cs
                best_model = _m
    if not best_model or best_model == "—":
        _sel = eval_result.get("selected_models") or list(model_stats.keys())
        best_model = _sel[0] if _sel else "—"
    best_display = MODEL_DISPLAY_NAMES.get(best_model, best_model)

    # ── 차트 임시 파일 목록 ────────────────────────────────────────────────────
    _chart_tmps: list[str] = []

    def _fig_to_tmp(fig: "go.Figure", w: int, h: int, scale: int = 2) -> str | None:
        try:
            fig.update_layout(width=w, height=h)
            img_bytes = fig.to_image(format="png", scale=scale)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_bytes)
                _chart_tmps.append(tmp.name)
                return tmp.name
        except Exception as ex:
            st.warning(f"차트 PNG 변환 실패: {ex}")
            return None

    kaleido_ok = importlib.util.find_spec("kaleido") is not None
    if not kaleido_ok:
        st.warning("kaleido 미설치 — 차트 없이 PDF 생성합니다.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ■ 1. 헤더
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        domain_key = eval_result.get("domain", "")
        domain_kr  = DOMAIN_NAMES.get(domain_key, domain_key) if domain_key else "—"
        session_id = eval_result.get("eval_session_id", "—")
        hdr = Table(
            [[
                Paragraph("BenchMate", s_logo),
                Paragraph(
                    f"문서번호: {session_id}  /  평가일: {date_str_kst}  /  도메인: {domain_kr}",
                    s_docinfo,
                ),
            ]],
            colWidths=[content_w * 0.4, content_w * 0.6],
        )
        hdr.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",  (1, 0), (1, 0),   "RIGHT"),
        ]))
        elems += [
            hdr,
            Spacer(1, 3),
            HRFlowable(width="100%", thickness=1.5, color=BLACK, spaceAfter=4),
        ]
    except Exception as e:
        st.warning(f"PDF 헤더 생성 오류: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ■ 2. KPI 카드 4개
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        best_score       = 0.0
        best_score_model = "—"
        for m, d in model_stats.items():
            if d.get("has_knowledge") and d["knowledge_total"] > best_score:
                best_score       = d["knowledge_total"]
                best_score_model = MODEL_DISPLAY_NAMES.get(m, m)

        if has_k and best_score > 0:
            kpi_score_val = f"{best_score:.1f}/25"
            kpi_score_sub = best_score_model
        elif has_a:
            kpi_score_val = "Agent 평가 결과"
            kpi_score_sub = "하단 표 참조"
        else:
            kpi_score_val = "미평가"
            kpi_score_sub = "—"

        eff_model_name = "—"
        eff_ratio_str  = "—"
        if cost_dict and has_k:
            best_eff = -1.0
            for m, d in model_stats.items():
                cv = cost_dict.get(m) or 0.0
                if cv > 0 and d.get("has_knowledge"):
                    ratio = d["knowledge_total"] / cv
                    if ratio > best_eff:
                        best_eff = ratio
                        eff_model_name = MODEL_DISPLAY_NAMES.get(m, m)
                        eff_ratio_str  = f"{d['knowledge_total']:.1f}pt / ${cv:.4f}"

        reliability = (
            st.session_state.get("judge_reliability")
            or eval_result.get("judge_reliability")
        )
        reliability_str = f"{reliability:.0f}%" if reliability is not None else "미측정"

        cw4 = content_w / 4
        kpi_tbl = Table(
            [[
                [Paragraph("추천 모델", s_kpi_lbl_w),
                 Paragraph(f"{best_display} ★", s_kpi_val_w),
                 Paragraph("(1순위)", s_kpi_sub_w)],
                [Paragraph("최고 지식점수", s_kpi_lbl),
                 Paragraph(kpi_score_val, s_kpi_val),
                 Paragraph(kpi_score_sub, s_kpi_sub)],
                [Paragraph("비용 효율 최고", s_kpi_lbl),
                 Paragraph(eff_model_name, s_kpi_val),
                 Paragraph(eff_ratio_str, s_kpi_sub)],
                [Paragraph("Judge 신뢰도", s_kpi_lbl),
                 Paragraph(reliability_str, s_kpi_val)],
            ]],
            colWidths=[cw4, cw4, cw4, cw4],
        )
        kpi_tbl.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND",    (0, 0), (0, 0),   ACCENT_BLUE),
            ("BACKGROUND",    (1, 0), (1, 0),   LIGHT_GRAY),
            ("BACKGROUND",    (2, 0), (2, 0),   LIGHT_GRAY),
            ("BACKGROUND",    (3, 0), (3, 0),   LIGHT_GRAY),
            ("BOX",           (0, 0), (0, 0),   1,   ACCENT_BLUE),
            ("BOX",           (1, 0), (1, 0),   0.5, BORDER_GRAY),
            ("BOX",           (2, 0), (2, 0),   0.5, BORDER_GRAY),
            ("BOX",           (3, 0), (3, 0),   0.5, BORDER_GRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ]))
        elems += [kpi_tbl, Spacer(1, 4)]
    except Exception as e:
        st.warning(f"PDF KPI 카드 생성 오류: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ■ 3. 레이더 차트
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if kaleido_ok:
        try:
            _RADAR_SHORT = ["정확도", "자연성", "허위정보", "전문성", "적절성"]
            if has_k:
                radar_fig = go.Figure()
                _plotted  = False
                for i, (model, data) in enumerate(model_stats.items()):
                    axes = data["knowledge_axes"]
                    vals = [axes.get(k, 0.0) for k in KNOWLEDGE_KEYS]
                    if all(v == 0.0 for v in vals):
                        continue
                    color = _CHART_COLORS[i % len(_CHART_COLORS)]
                    radar_fig.add_trace(go.Scatterpolar(
                        r=vals + [vals[0]],
                        theta=_RADAR_SHORT + [_RADAR_SHORT[0]],
                        fill="toself",
                        name=MODEL_DISPLAY_NAMES.get(model, model),
                        line=dict(color=color),
                        fillcolor=color,
                        opacity=0.25,
                    ))
                    _plotted = True
                if _plotted:
                    radar_fig.update_layout(
                        polar=dict(
                            radialaxis=dict(visible=True, range=[0, 5],
                                            tickfont=dict(size=7)),
                            angularaxis=dict(tickfont=dict(size=8)),
                        ),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                    xanchor="right", x=1, font=dict(size=8)),
                        font=dict(size=8),
                        margin=dict(l=40, r=40, t=30, b=20),
                    )
                    p = _fig_to_tmp(radar_fig, 380, 220, scale=2)
                    if p:
                        radar_w = content_w * 380 / 460
                        radar_h = radar_w * 220 / 380
                        radar_img = Image(p, width=radar_w, height=radar_h, hAlign="CENTER")
                        radar_tbl = Table([[radar_img]], colWidths=[content_w])
                        radar_tbl.setStyle(TableStyle([
                            ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ]))
                        cap_tbl = Table(
                            [[Paragraph("Knowledge 5축 레이더 차트", s_caption)]],
                            colWidths=[content_w],
                        )
                        cap_tbl.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
                        elems += [radar_tbl, Spacer(1, 2), cap_tbl, Spacer(1, 4)]
        except Exception as e:
            st.warning(f"PDF 레이더 차트 생성 오류: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ■ 4. 바 차트
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if kaleido_ok:
        try:
            if has_k:
                models_k      = [m for m, d in model_stats.items() if d.get("has_knowledge")]
                display_names = [MODEL_DISPLAY_NAMES.get(m, m) for m in models_k]
                scores_k      = [round(model_stats[m]["knowledge_total"], 1) for m in models_k]
                sorted_models = sorted(models_k, key=lambda m: model_stats[m]["knowledge_total"], reverse=True)
                rank_map      = {m: i for i, m in enumerate(sorted_models)}
                bar_colors    = [_RANK_COLORS[min(rank_map[m], len(_RANK_COLORS) - 1)] for m in models_k]

                bar_fig = go.Figure(go.Bar(
                    y=display_names, x=scores_k, orientation="h",
                    marker_color=bar_colors,
                    text=[str(s) for s in scores_k],
                    textposition="outside",
                    textfont=dict(size=6, color="#1A1A1A"),
                ))
                bar_fig.update_layout(
                    plot_bgcolor="white", paper_bgcolor="white",
                    margin=dict(l=60, r=40, t=10, b=10),
                    xaxis=dict(range=[0, 25], showgrid=True, gridcolor="#eeeeee",
                               tickfont=dict(size=6)),
                    yaxis=dict(showgrid=False, tickfont=dict(size=6)),
                    font=dict(family="Arial", size=6),
                    showlegend=False,
                )
                p = _fig_to_tmp(bar_fig, 390, 95, scale=2)
                if p:
                    elems += [
                        Image(p, width=content_w, height=content_w * 95 / 390),
                        Spacer(1, 2),
                        Paragraph("Knowledge 총점 비교 (25점 만점)", s_caption),
                        Spacer(1, 4),
                    ]
        except Exception as e:
            st.warning(f"PDF 바 차트 생성 오류: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ■ 5. 핵심 발견 — 좌측 ACCENT_BLUE 세로 바
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        strengths_all = _extract_bullets(report_text, "강점 분석")
        insight_raw   = (
            strengths_all[0]
            if strengths_all
            else _extract_section(report_text, "핵심 발견") or "—"
        )
        insight_text = insight_raw[:110] + ("…" if len(insight_raw) > 110 else "")
        insight_tbl = Table(
            [["", [Paragraph("■ 핵심 발견", s_sec_hd), Spacer(1, 2),
                   Paragraph(insight_text, s_insight)]]],
            colWidths=[4, content_w - 4],
        )
        insight_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0),   ACCENT_BLUE),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (0, 0),   0),
            ("RIGHTPADDING",  (0, 0), (0, 0),   0),
            ("LEFTPADDING",   (1, 0), (1, 0),   8),
            ("RIGHTPADDING",  (1, 0), (1, 0),   0),
        ]))
        elems += [insight_tbl, Spacer(1, 4)]
    except Exception as e:
        st.warning(f"PDF 핵심 발견 생성 오류: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ■ 6. 강점 / 리스크 2컬럼
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        strengths = _extract_bullets(report_text, "강점 분석")
        risks     = _extract_bullets(report_text, "리스크 & 권고")

        def _bullet_cell(items: list[str]) -> list:
            cell: list = []
            for item in (items or ["—"])[:2]:
                txt = item[:65] + ("…" if len(item) > 65 else "")
                cell.append(Paragraph(f"• {txt}", s_bullet))
            return cell

        cw_half = content_w / 2 - 3
        findings_tbl = Table(
            [
                [Paragraph("■ 강점 분석", s_sec_hd_w),
                 Paragraph("■ 리스크 & 권고", s_sec_hd_w)],
                [_bullet_cell(strengths), _bullet_cell(risks)],
            ],
            colWidths=[cw_half, cw_half],
        )
        findings_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0),   ACCENT_BLUE),
            ("BACKGROUND",    (1, 0), (1, 0),   DARK_GRAY),
            ("BACKGROUND",    (0, 1), (0, 1),   LIGHT_GRAY),
            ("BACKGROUND",    (1, 1), (1, 1),   LIGHT_GRAY),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("BOX",           (0, 0), (0, 1),   0.5, BORDER_GRAY),
            ("BOX",           (1, 0), (1, 1),   0.5, BORDER_GRAY),
        ]))
        elems += [findings_tbl, Spacer(1, 4)]
    except Exception as e:
        st.warning(f"PDF 강점/리스크 섹션 생성 오류: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ■ 7. 모델 성과 비교 표
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        _k_axis_keys    = ["accuracy", "hallucination", "domain_expertise"]
        _agent_tbl_keys = ["call", "slot", "relevance", "completion"]
        _agent_tbl_hdrs = ["Tool호출", "슬롯", "거절", "완료"]
        col_hdrs = ["모델"]
        if has_k:
            col_hdrs += ["지식총점(/25)", "사실정확도", "허위정보없음", "도메인전문성"]
        if has_a:
            col_hdrs += _agent_tbl_hdrs
        if cost_dict:
            col_hdrs += ["비용(USD)", "비용(KRW)"]

        n_cols   = len(col_hdrs)
        cw_model = content_w * 0.18
        cw_rest  = (content_w - cw_model) / max(n_cols - 1, 1)

        k_models    = [d for d in model_stats.values() if d.get("has_knowledge")]
        best_total  = max((d["knowledge_total"] for d in k_models), default=None) if k_models else None
        worst_total = min((d["knowledge_total"] for d in k_models), default=None) if len(k_models) > 1 else None
        best_axis:  dict[str, float] = {}
        worst_axis: dict[str, float] = {}
        if has_k and k_models:
            for ak in _k_axis_keys:
                vals = [d["knowledge_axes"].get(ak, 0) for d in k_models]
                best_axis[ak] = max(vals)
                if len(vals) > 1:
                    worst_axis[ak] = min(vals)

        _cell_bg: dict[tuple[int, int], object] = {}
        tbl_data = [[Paragraph(h, s_th) for h in col_hdrs]]

        for row_i, (model, data) in enumerate(model_stats.items(), start=1):
            is_best = (model == best_model)
            s_name  = s_td_hi  if is_best else s_td
            s_num   = s_td_hic if is_best else s_td_c
            row = [Paragraph(MODEL_DISPLAY_NAMES.get(model, model), s_name)]

            if has_k:
                kt = data["knowledge_total"]
                is_kt_best  = (kt == best_total)
                is_kt_worst = (kt == worst_total) and worst_total is not None
                s_kt = _stb(f"kt_{row_i}", fontSize=7.5, leading=10,
                             textColor=BLACK if is_best else DARK_GRAY, alignment=1) \
                       if is_kt_best else s_num
                row.append(Paragraph(f"{kt:.1f}", s_kt))
                if is_kt_best and not is_best:
                    _cell_bg[(row_i, 1)] = CELL_BEST

                for ak_i, ak in enumerate(_k_axis_keys, start=2):
                    v = data["knowledge_axes"].get(ak, 0)
                    is_v_best   = (v == best_axis.get(ak))
                    is_v_danger = (ak == "hallucination" and v <= 2.0)
                    s_v = _stb(f"av_{row_i}_{ak}", fontSize=7.5, leading=10,
                                textColor=BLACK if is_best else DARK_GRAY, alignment=1) \
                          if is_v_best else s_num
                    row.append(Paragraph(f"{v:.2f}", s_v))
                    if is_v_danger:
                        _cell_bg[(row_i, ak_i)] = CELL_DANGER
                    elif is_v_best and not is_best:
                        _cell_bg[(row_i, ak_i)] = CELL_BEST

            if has_a:
                a_scores = data.get("agent_scores", {})
                for _ak in _agent_tbl_keys:
                    _av = a_scores.get(_ak, 0.0)
                    _av = float(_av) if isinstance(_av, (int, float)) else 0.0
                    row.append(Paragraph(f"{_av:.2f}", s_num))

            if cost_dict:
                cv  = float(cost_dict.get(model) or 0.0)
                krw = cv * USD_TO_KRW
                row.append(Paragraph(f"${cv:.4f}", s_num))
                row.append(Paragraph(f"₩{krw:,.0f}", s_num))
            tbl_data.append(row)

        row_h = [16] + [14] * (len(tbl_data) - 1)
        model_style: list = [
            ("BACKGROUND",    (0, 0), (-1, 0),  BLACK),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
            ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",          (0, 0), (-1, -1), 0.3, BORDER_GRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("FONTNAME",      (0, 0), (-1, -1), _FN),
            ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ]
        for i, (model, _) in enumerate(model_stats.items(), start=1):
            if model == best_model:
                model_style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#EFF6FF")))
                model_style.append(("LINEBELOW",  (0, i), (-1, i), 1, ACCENT_BLUE))
            elif i % 2 == 0:
                model_style.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GRAY))
        for (r, c), bg in _cell_bg.items():
            model_style.append(("BACKGROUND", (c, r), (c, r), bg))

        model_tbl = Table(
            tbl_data,
            colWidths=[cw_model] + [cw_rest] * (n_cols - 1),
            rowHeights=row_h,
        )
        model_tbl.setStyle(TableStyle(model_style))

        legend_para = Paragraph(
            "★ 최고값 (앰버 배경)   ▽ 허위정보 점수 ≤ 2 (빨강 배경)",
            s_legend,
        )
        elems += [model_tbl, Spacer(1, 2), legend_para]
        if cost_dict:
            elems.append(Paragraph(
                f"※ 환율 기준: USD 1 = KRW {USD_TO_KRW:,} ({date_str_kst} 기준)",
                s_footnote,
            ))
        elems.append(Spacer(1, 4))
    except Exception as e:
        st.warning(f"PDF 모델 비교 표 생성 오류: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ■ 8. 푸터
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        elems += [
            Spacer(1, 4),
            HRFlowable(width="100%", thickness=0.5, color=BORDER_GRAY, spaceAfter=3),
            Paragraph(
                "본 리포트는 BenchMate AI 자동 분석 결과입니다. "
                "최종 의사결정은 담당자가 내려주세요.",
                s_footer,
            ),
        ]
    except Exception as e:
        st.warning(f"PDF 푸터 생성 오류: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # doc.build
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        doc.build(elems)
        return buf.getvalue()
    except Exception as e:
        st.warning(f"PDF 최종 빌드 실패: {e}")
        return None
    finally:
        for p in _chart_tmps:
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except OSError:
                pass


# ── 평가 개요 표 ───────────────────────────────────────────────────────────────

def _render_overview_table(eval_result: dict) -> None:
    st.subheader("평가 개요")
    domain_key = eval_result.get("domain", "")
    domain_kr = DOMAIN_NAMES.get(domain_key, domain_key) if domain_key else "—"
    eval_mode = eval_result.get("eval_mode", "—")
    session_id = eval_result.get("eval_session_id", "—")
    model_count = len((eval_result.get("summary_table") or {}).keys()) or "—"
    q_count = 0
    s_count = 0
    for sections in (eval_result.get("summary_table") or {}).values():
        q_count = max(q_count, (sections.get("knowledge") or {}).get("question_count") or 0)
        s_count = max(s_count, (sections.get("agent") or {}).get("scenario_count") or 0)

    rows = [
        {"항목": "평가 도메인",         "값": domain_kr},
        {"항목": "평가 모드",           "값": eval_mode},
        {"항목": "평가 모델 수",         "값": str(model_count)},
        {"항목": "Knowledge 문항 수",   "값": str(q_count) if q_count else "—"},
        {"항목": "Agent 시나리오 수",   "값": str(s_count) if s_count else "—"},
        {"항목": "세션 ID",             "값": session_id},
    ]
    st.table(rows)


# ── 점수 비교 표 ───────────────────────────────────────────────────────────────

def _render_score_table(model_stats: dict[str, dict]) -> None:
    st.subheader("점수 비교")
    has_k = has_knowledge_data(model_stats)
    has_a_any = any(d.get("has_agent") for d in model_stats.values())

    table_rows = []
    for model, data in model_stats.items():
        row: dict = {"모델": MODEL_DISPLAY_NAMES.get(model, model)}
        if has_k:
            row["Knowledge 총점"] = f"{data['knowledge_total']:.1f}"
            for key, label in zip(KNOWLEDGE_KEYS, KNOWLEDGE_AXES):
                row[label] = f"{data['knowledge_axes'].get(key, 0.0):.2f}"
        if has_a_any and data.get("has_agent"):
            a = data["agent_scores"]
            for key in AGENT_ITEMS:
                row[AGENT_LABELS[key]] = f"{a.get(key, 0.0):.2f}"
        table_rows.append(row)

    if table_rows:
        st.dataframe(table_rows, use_container_width=True)


# ── 차트 섹션 ──────────────────────────────────────────────────────────────────

def _render_charts(model_stats: dict[str, dict], eval_result: dict) -> None:
    st.subheader("시각화")
    eval_mode = st.session_state.get("eval_mode", "")
    has_k = has_knowledge_data(model_stats)
    has_a = has_agent_data(model_stats, eval_result, eval_mode)

    if has_k and has_a:
        st.plotly_chart(build_scatter_fig(model_stats), use_container_width=True)
    elif has_k:
        st.plotly_chart(build_knowledge_bar_fig(model_stats), use_container_width=True)

    col_l, col_r = st.columns(2)
    with col_l:
        if has_k:
            radar_fig = build_radar_fig(model_stats)
            if radar_fig:
                st.plotly_chart(radar_fig, use_container_width=True)
    with col_r:
        if has_a:
            agent_fig = build_agent_bar_fig(model_stats)
            if agent_fig:
                st.plotly_chart(agent_fig, use_container_width=True)


# ── 비용 분석 표 ───────────────────────────────────────────────────────────────

def _render_cost_table(eval_result: dict) -> None:
    cost_dict: dict | None = eval_result.get("estimated_cost")
    if not cost_dict:
        return
    st.subheader("비용 분석")
    rows = []
    total = 0.0
    for k, v in cost_dict.items():
        if k == "_total" or not isinstance(v, (int, float)):
            continue
        rows.append({"항목": k, "비용 (USD)": f"${v:.4f}"})
        total += v
    rows.append({"항목": "**합계**", "비용 (USD)": f"**${total:.4f}**"})
    st.table(rows)


# ── 내보내기 버튼 ───────────────────────────────────────────────────────────────

def _render_export_buttons(
    eval_result: dict,
    model_stats: dict[str, dict],
    report_text: str,
) -> None:
    st.subheader("내보내기")

    pdf_bytes = _build_mckinsey_pdf(eval_result, model_stats, report_text)
    col_md, col_pdf, col_json = st.columns(3)

    with col_md:
        st.download_button(
            label="리포트 다운로드 (Markdown)",
            data=report_text.encode("utf-8"),
            file_name="benchmate_report.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_pdf:
        if pdf_bytes:
            st.download_button(
                label="리포트 다운로드 (PDF)",
                data=pdf_bytes,
                file_name="benchmate_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.warning("PDF 빌드에 실패했습니다. 위 경고 메시지를 확인하세요.")
            st.download_button(
                label="PDF 다운로드",
                data=b"",
                file_name="benchmate_report.pdf",
                mime="application/pdf",
                disabled=True,
                use_container_width=True,
            )

    with col_json:
        session_path = _find_session_json(eval_result)
        if session_path:
            json_bytes = session_path.read_bytes()
            st.download_button(
                label="전체 결과 다운로드 (JSON)",
                data=json_bytes,
                file_name=session_path.name,
                mime="application/json",
                use_container_width=True,
            )
        else:
            fallback_json = json.dumps(eval_result, ensure_ascii=False, indent=2)
            st.download_button(
                label="전체 결과 다운로드 (JSON)",
                data=fallback_json.encode("utf-8"),
                file_name="benchmate_result.json",
                mime="application/json",
                use_container_width=True,
            )


# ── render ─────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("BenchMate")
    st.write("PM 해석 리포트")
    st.divider()

    eval_result: dict | None = st.session_state.get("eval_result")
    report_text: str = (eval_result or {}).get("pm_report_text", "")

    st.info(
        "이 리포트는 AI가 자동 생성했습니다. "
        "참고 자료로 활용하시고 최종 결정은 담당자가 내려주세요."
    )

    if not eval_result or not report_text:
        st.warning("리포트가 없습니다. 평가를 먼저 실행해주세요.")
        if st.button("처음으로", use_container_width=False):
            st.session_state.clear()
            st.session_state["current_screen"] = 1
            st.rerun()
        return

    model_stats = extract_model_stats(eval_result)

    # ── Section 1: 평가 개요 ──────────────────────────────────────────────────
    _render_overview_table(eval_result)
    st.divider()

    # ── Section 2: 추천 모델 ──────────────────────────────────────────────────
    st.subheader("추천 모델")
    best = _get_best_model(eval_result.get("summary_table") or {})
    st.success(f"추천 모델: **{MODEL_DISPLAY_NAMES.get(best, best)}**")
    st.divider()

    # ── Section 3: 점수 비교 ──────────────────────────────────────────────────
    _render_score_table(model_stats)
    st.divider()

    # ── Section 4: 차트 ───────────────────────────────────────────────────────
    _render_charts(model_stats, eval_result)
    st.divider()

    # ── Section 5: AI 분석 요약 ───────────────────────────────────────────────
    st.subheader("AI 분석 요약")
    ai_text = _extract_ai_analysis(report_text)
    st.markdown(ai_text if ai_text else report_text)
    st.divider()

    # ── Section 6: 비용 분석 ──────────────────────────────────────────────────
    _render_cost_table(eval_result)
    st.divider()

    # ── 내보내기 버튼 ─────────────────────────────────────────────────────────
    _render_export_buttons(eval_result, model_stats, report_text)
    st.divider()

    # ── 하단 네비게이션 ───────────────────────────────────────────────────────
    col_dash, col_review, col_restart = st.columns(3)
    with col_dash:
        if st.button("← 대시보드로", use_container_width=True):
            st.session_state["current_screen"] = 5
            st.rerun()
    with col_review:
        if st.button("← Human Review로", use_container_width=True):
            st.session_state["current_screen"] = 6
            st.rerun()
    with col_restart:
        if st.button("처음부터 다시 평가하기", type="secondary", use_container_width=True):
            st.session_state.clear()
            st.session_state["current_screen"] = 1
            st.rerun()
