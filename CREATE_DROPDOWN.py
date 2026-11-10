from pathlib import Path
import re
import py_compile

source = Path("SEA_SENTINEL_VISUAL_RISK_REDESIGNED.py")
target = Path("SEA_SENTINEL_V2_DROPDOWN_FIXED.py")

if not source.exists():
    raise SystemExit("ERROR: Original dashboard file not found.")

code = source.read_text(encoding="utf-8-sig")

start = code.find("with st.sidebar:")
end = code.find("\npage=st.session_state.page", start)

if start == -1 or end == -1:
    raise SystemExit("ERROR: Could not locate the original sidebar. No changes made.")

sidebar = '''
st.markdown("""
<style>
[data-testid="stSidebar"] [data-testid="stExpander"] details > summary,
[data-testid="stSidebar"] [data-testid="stExpander"] details > summary[aria-expanded="true"] {
    background: #0a2a40 !important;
    color: #eaffff !important;
    border-radius: 9px !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] details > summary *,
[data-testid="stSidebar"] [data-testid="stExpander"] details > summary p {
    color: #eaffff !important;
    fill: #eaffff !important;
    font-weight: 750 !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] details > summary svg {
    color: #35e6ff !important;
    stroke: #35e6ff !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] .stButton button {
    min-height: 36px !important;
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown(
        "<div class='sea-brand'><div class='sea-brand-mark'>⚓</div>"
        "<div><div class='sea-brand-title'>SEA SENTINEL</div></div></div>",
        unsafe_allow_html=True
    )
    st.divider()

    if 'page' not in st.session_state:
        st.session_state.page = 'Overview'

    nav_icons = {
        'DETECTION CENTRE': '◈',
        'VESSEL INTELLIGENCE': '⚓',
        'ANALYTICS & MONITORING': '▥'
    }

    for group, items in NAV.items():
        active = st.session_state.page in items

        with st.expander(
            f"{nav_icons.get(group, '▸')}  {group.title()}",
            expanded=active
        ):
            for name in items:
                if st.button(
                    f"{ICONS[name]}   {name}",
                    key='nav_' + name,
                    use_container_width=True,
                    type='primary' if st.session_state.page == name else 'secondary'
                ):
                    st.session_state.page = name
                    st.rerun()

'''

updated = code[:start] + sidebar + code[end:]
target.write_text(updated, encoding="utf-8")
py_compile.compile(str(target), doraise=True)

print("SUCCESS: Dropdown dashboard created!")
print("File:", target.resolve())
