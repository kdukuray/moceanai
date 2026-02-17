"""
MoceanAI V2 -- Main Streamlit Application

Run from project root:
    streamlit run v2/app.py
"""

import sys
from pathlib import Path

# Ensure the project root is on the Python path so v2.* imports work
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import streamlit as st
from v2.core.database import init_db

# Initialize database tables on first load
init_db()

# Page configuration
st.set_page_config(
    page_title="MoceanAI V2",
    page_icon="M",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Define pages using file paths relative to this script
pages_dir = Path(__file__).parent / "pages"

short_form_page = st.Page(str(pages_dir / "short_form.py"), title="Short Form", icon=":material/movie:")
long_form_page = st.Page(str(pages_dir / "long_form.py"), title="Long Form", icon=":material/theaters:")
short_form_v2_page = st.Page(str(pages_dir / "short_form_v2.py"), title="Short Form V2", icon=":material/movie_filter:")
long_form_v2_page = st.Page(str(pages_dir / "long_form_v2.py"), title="Long Form V2", icon=":material/featured_video:")
ebook_page = st.Page(str(pages_dir / "ebook.py"), title="Ebook", icon=":material/menu_book:")
ugc_page = st.Page(str(pages_dir / "ugc.py"), title="UGC Product", icon=":material/shopping_bag:")
profiles_page = st.Page(str(pages_dir / "profiles.py"), title="Profiles", icon=":material/person:")
history_page = st.Page(str(pages_dir / "history.py"), title="History", icon=":material/history:")

# Navigation
pg = st.navigation(
    {
        "Create": [short_form_page, long_form_page, short_form_v2_page, long_form_v2_page, ebook_page, ugc_page],
        "Manage": [profiles_page, history_page],
    }
)

# Sidebar branding
with st.sidebar:
    st.markdown("---")
    st.caption("MoceanAI V2 -- AI Content Generation")

pg.run()
