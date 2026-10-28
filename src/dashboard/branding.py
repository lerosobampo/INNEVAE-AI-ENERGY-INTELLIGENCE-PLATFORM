"""Official INNEVA.E branding for the Streamlit dashboard."""
from __future__ import annotations

import base64
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "assets" / "innevae_logo.png"


def apply_branding() -> None:
    """Render the top-aligned horizontal brand lockup and shared styling."""
    st.markdown("""
    <style>
      [data-testid="stSidebar"] { background: #073B21 !important; }
      [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        padding-top: 0.5rem !important;
      }
      [data-testid="stSidebar"] p,
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] h1,
      [data-testid="stSidebar"] h2,
      [data-testid="stSidebar"] h3,
      [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: #FFFFFF !important;
      }
      /* Navigation: flat white line icons, no emoji or radio circles. */
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label {
        position: relative;
        display: flex !important;
        align-items: center !important;
        padding: 0.65rem 0.7rem 0.65rem 2.8rem !important;
        margin-bottom: 0.12rem;
        cursor: pointer;
        border-radius: 8px;
        transition: background-color 150ms ease;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:hover {
        background: #12532F;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
        background: #17643A;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label > div:has(input[type="radio"]) {
        position: absolute !important;
        width: 1px !important;
        height: 1px !important;
        opacity: 0 !important;
        overflow: hidden !important;
      }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label::before {
        content: "";
        position: absolute;
        left: 0.7rem;
        top: 50%;
        transform: translateY(-50%);
        width: 19px;
        height: 19px;
        background-repeat: no-repeat;
        background-position: center;
        background-size: contain;
      }

      /* Each icon is an inline, white SVG asset (no external dependency). */
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(1)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Crect%20x%3D%223%22%20y%3D%228%22%20width%3D%2218%22%20height%3D%2213%22%20rx%3D%222%22%2F%3E%3Cpath%20d%3D%22M12%202v6M9%202h6M8%2013h.01M16%2013h.01M8%2017h8%22%2F%3E%3C%2Fsvg%3E"); }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(2)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22m13%202-3%208h7l-6%2012%202-9H6z%22%2F%3E%3C%2Fsvg%3E"); }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(3)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M3%203v18h18%22%2F%3E%3Cpath%20d%3D%22m7%2016%204-5%204%203%205-7%22%2F%3E%3C%2Fsvg%3E"); }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(4)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M20%207v5h-5M4%2017v-5h5%22%2F%3E%3Cpath%20d%3D%22M5.6%209A7%207%200%200%201%2018%206l2%201M4%2017l2%201a7%207%200%200%200%2012.4-3%22%2F%3E%3C%2Fsvg%3E"); }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(5)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M12%2018V5a3%203%200%200%200-6%200%204%204%200%200%200-2%207%204%204%200%200%200%203%207%203%203%200%200%200%205-1ZM12%2018V5a3%203%200%200%201%206%200%204%204%200%200%201%202%207%204%204%200%200%201-3%207%203%203%200%200%201-5-1Z%22%2F%3E%3C%2Fsvg%3E"); }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(6)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Ccircle%20cx%3D%2212%22%20cy%3D%2212%22%20r%3D%223%22%2F%3E%3Cpath%20d%3D%22M19.4%2015a1.7%201.7%200%200%200%20.34%201.87l.06.06-1.9%201.9-.06-.06A1.7%201.7%200%200%200%2016%2018.4a1.7%201.7%200%200%200-1%201.56V21h-3v-1.04A1.7%201.7%200%200%200%2011%2018.4a1.7%201.7%200%200%200-1.87.34l-.06.06-1.9-1.9.06-.06A1.7%201.7%200%200%200%207.6%2015a1.7%201.7%200%200%200-1.56-1H5v-3h1.04A1.7%201.7%200%200%200%207.6%2010a1.7%201.7%200%200%200-.34-1.87L7.2%208.07l1.9-1.9.06.06A1.7%201.7%200%200%200%2011%206.6a1.7%201.7%200%200%200%201-1.56V4h3v1.04A1.7%201.7%200%200%200%2016%206.6a1.7%201.7%200%200%200%201.87-.34l.06-.06%201.9%201.9-.06.06A1.7%201.7%200%200%200%2019.4%2010a1.7%201.7%200%200%200%201.56%201H22v3h-1.04A1.7%201.7%200%200%200%2019.4%2015Z%22%2F%3E%3C%2Fsvg%3E"); }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(7)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Crect%20x%3D%223%22%20y%3D%224%22%20width%3D%2218%22%20height%3D%2215%22%20rx%3D%222%22%2F%3E%3Cpath%20d%3D%22M8%2022h8M12%2019v3M7%209h4M7%2013h7%22%2F%3E%3C%2Fsvg%3E"); }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(8)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M12%2022s8-4%208-10V5l-8-3-8%203v7c0%206%208%2010%208%2010Z%22%2F%3E%3Cpath%20d%3D%22m9%2012%202%202%204-4%22%2F%3E%3C%2Fsvg%3E"); }
      [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:nth-child(9)::before { background-image: url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23FFFFFF%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M4%2019V5M4%2019h16M8%2016v-5M12%2016V8M16%2016v-8M20%2016V5%22%2F%3E%3C%2Fsvg%3E"); }
      /* Left-align the custom icon buttons without changing their colors. */
      [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button {
        display: flex !important;
        justify-content: flex-start !important;
        text-align: left !important;
        padding-left: 14px !important;
      }
      [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button > div,
      [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button > span,
      [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button [data-testid="stMarkdownContainer"] {
        justify-content: flex-start !important;
        text-align: left !important;
      }
      [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button > div {
        width: 100% !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
      }
      [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button p {
        text-align: left !important;
        margin: 0 !important;
      }

      div.stButton > button, div.stDownloadButton > button,
      div.stFormSubmitButton > button, div.stPopover > button {
        background-color: #078A19 !important;
        border: 1px solid #078A19 !important;
        color: #FFFFFF !important;
      }
      div.stButton > button:hover, div.stDownloadButton > button:hover,
      div.stFormSubmitButton > button:hover, div.stPopover > button:hover {
        background-color: #066B15 !important;
        border-color: #066B15 !important;
        color: #FFFFFF !important;
      }
      div.stButton > button:focus-visible,
      div.stDownloadButton > button:focus-visible,
      div.stFormSubmitButton > button:focus-visible {
        outline: 2px solid #7BB43A;
      }
      .innevae-brand-row {
        display: flex;
        align-items: center;
        gap: 12px;
        width: 100%;
        padding: 0 0 4px 0;
      }
      .innevae-brand-logo {
        display: block;
        width: 60px;
        height: 60px;
        object-fit: contain;
        flex-shrink: 0;
      }
      .innevae-brand-name {
        font-family: inherit;
        font-weight: 800;
        font-size: 1.55rem;
        letter-spacing: 0.015em;
        white-space: nowrap;
        line-height: 1;
        color: #FFFFFF;
      }
      .innevae-brand-name span { color: #7BB43A; }
      .innevae-brand-subtitle {
        color: #CDE6D3;
        font-size: 0.77rem;
        margin-top: 6px;
        margin-bottom: 2px;
      }
    </style>
    """, unsafe_allow_html=True)

    if not LOGO.is_file():
        raise FileNotFoundError(f"INNEVA.E logo not found: {LOGO}")

    encoded_logo = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    st.sidebar.markdown(
        f"""
        <div class="innevae-brand-row">
          <img class="innevae-brand-logo" src="data:image/png;base64,{encoded_logo}"
               alt="INNEVA.E official logo" />
          <div class="innevae-brand-name">INNEVA.<span>E</span></div>
        </div>
        <div class="innevae-brand-subtitle">AI Energy Intelligence Platform</div>
        """,
        unsafe_allow_html=True,
    )
