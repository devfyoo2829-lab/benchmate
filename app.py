import streamlit as st

st.set_page_config(
    page_title="BenchMate",
    page_icon="⚡",
    layout="wide",
)

if "current_screen" not in st.session_state:
    st.session_state["current_screen"] = 1

screen = st.session_state["current_screen"]

if screen == 1:
    from ui.screen1_mode_select import render
    render()
elif screen == 2:
    from ui.screen2_domain_tool import render
    render()
elif screen == 3:
    from ui.screen3_scenario import render
    render()
else:
    st.info(f"Screen {screen} — 준비 중입니다.")
    if st.button("← 처음으로"):
        st.session_state["current_screen"] = 1
        st.rerun()
