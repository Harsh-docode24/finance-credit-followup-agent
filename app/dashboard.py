"""
Streamlit Dashboard — Finance Credit Follow-Up Email Agent
===========================================================
Interactive UI for:
- Uploading credit records
- Viewing overdue records
- Triggering the agent
- Viewing generated emails
- Browsing the audit trail
- Dashboard with key metrics
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import json

from src.config import (
    ESCALATION_MATRIX,
    get_escalation_stage,
    COMPANY_NAME,
    EMAIL_MODE,
)
from src.models import CreditRecord, SendStatus
from src.data_ingestion import load_credit_records
from src.audit_trail import (
    init_database,
    get_audit_logs,
    get_audit_summary,
    export_audit_to_json,
)

# ── Page Configuration ────────────────────────────────────
st.set_page_config(
    page_title=f"Finance Credit Agent — {COMPANY_NAME}",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS for Premium Look ───────────────────────────
st.markdown("""
<style>
    /* Main theme */
    .stApp {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #0f0f23 100%);
    }
    
    /* Metric cards */
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 16px;
        backdrop-filter: blur(10px);
    }
    
    div[data-testid="metric-container"] label {
        color: #8b8baa !important;
        font-size: 0.85rem !important;
    }
    
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 2rem !important;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #e0e0ff !important;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a3e, #0f0f23);
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    
    /* Tables */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: rgba(255,255,255,0.05);
        border-radius: 8px 8px 0 0;
        border: 1px solid rgba(255,255,255,0.1);
        color: #8b8baa;
    }
    
    .stTabs [aria-selected="true"] {
        background: rgba(99, 102, 241, 0.2) !important;
        border-color: #6366f1 !important;
        color: #ffffff !important;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 24px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
        transform: translateY(-1px);
    }
    
    /* Alert boxes */
    .stAlert {
        border-radius: 8px;
    }
    
    /* Success/Info containers */
    .stage-warm { border-left: 4px solid #22c55e; padding: 12px; background: rgba(34,197,94,0.1); border-radius: 8px; margin: 8px 0; }
    .stage-polite { border-left: 4px solid #eab308; padding: 12px; background: rgba(234,179,8,0.1); border-radius: 8px; margin: 8px 0; }
    .stage-formal { border-left: 4px solid #f97316; padding: 12px; background: rgba(249,115,22,0.1); border-radius: 8px; margin: 8px 0; }
    .stage-stern { border-left: 4px solid #ef4444; padding: 12px; background: rgba(239,68,68,0.1); border-radius: 8px; margin: 8px 0; }
    .stage-escalation { border-left: 4px solid #dc2626; padding: 12px; background: rgba(220,38,38,0.15); border-radius: 8px; margin: 8px 0; }
</style>
""", unsafe_allow_html=True)

# ── Initialize Database ───────────────────────────────────
init_database()


# ── Sidebar ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💰 Credit Agent")
    st.markdown(f"**Company:** {COMPANY_NAME}")
    st.markdown(f"**Email Mode:** `{EMAIL_MODE}`")
    st.divider()

    # File upload
    st.markdown("### 📂 Data Source")
    data_source = st.radio(
        "Choose data source:",
        ["Sample Data", "Upload CSV/Excel"],
        index=0,
    )

    uploaded_file = None
    data_file_path = "data/sample_credits.csv"

    if data_source == "Upload CSV/Excel":
        uploaded_file = st.file_uploader(
            "Upload credit records",
            type=["csv", "xlsx", "xls"],
        )
        if uploaded_file:
            # Save to temp location
            temp_path = Path("data") / f"uploaded_{uploaded_file.name}"
            temp_path.parent.mkdir(exist_ok=True)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getvalue())
            data_file_path = str(temp_path)
            st.success(f"✅ Loaded: {uploaded_file.name}")

    st.divider()

    # Escalation Matrix Reference
    st.markdown("### 📊 Escalation Matrix")
    for stage_num, config in ESCALATION_MATRIX.items():
        days_range = f"{config['trigger_days'][0]}–{config['trigger_days'][1] if config['trigger_days'][1] < 9999 else '∞'}"
        emoji = ["", "🟢", "🟡", "🟠", "🔴", "🚩"][stage_num]
        st.markdown(f"{emoji} **Stage {stage_num}:** {days_range}d — {config['tone']}")


# ── Load Data ─────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_data(file_path):
    try:
        records = load_credit_records(file_path)
        return records, None
    except Exception as e:
        return [], str(e)


records, load_error = load_data(data_file_path)

if load_error:
    st.error(f"❌ Failed to load data: {load_error}")
    st.stop()


# ── Main Content Area ─────────────────────────────────────
st.markdown("# 💰 Finance Credit Follow-Up Agent")
st.markdown("*AI-powered overdue payment follow-up system with tone escalation*")

# ── Tabs ──────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard",
    "📋 Credit Records",
    "🚀 Run Agent",
    "📧 Email Preview",
    "📋 Audit Trail",
])

# ══════════════════════════════════════════════════════════
# TAB 1: Dashboard
# ══════════════════════════════════════════════════════════
with tab1:
    st.markdown("## 📊 Overview Dashboard")

    # Calculate metrics
    total_records = len(records)
    overdue_records = [r for r in records if r.days_overdue > 0]
    total_overdue = len(overdue_records)
    total_amount = sum(r.amount_due for r in overdue_records)

    # Stage distribution
    stage_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in overdue_records:
        stage = get_escalation_stage(r.days_overdue, r.follow_up_count)
        if stage in stage_counts:
            stage_counts[stage] += 1

    # Metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Records", total_records)
    with col2:
        st.metric("Overdue", total_overdue, delta=f"{total_overdue/total_records*100:.0f}%" if total_records > 0 else "0%")
    with col3:
        st.metric("Total Outstanding", f"₹{total_amount:,.0f}")
    with col4:
        st.metric("Need Escalation", stage_counts.get(5, 0))
    with col5:
        audit = get_audit_summary()
        st.metric("Emails Logged", audit.get("total_entries", 0))

    st.divider()

    # Charts
    col_left, col_right = st.columns(2)

    with col_left:
        # Stage distribution chart
        stage_labels = [ESCALATION_MATRIX[s]["stage_name"] for s in range(1, 6)]
        stage_values = [stage_counts.get(s, 0) for s in range(1, 6)]
        colors = ["#22c55e", "#eab308", "#f97316", "#ef4444", "#dc2626"]

        fig_stages = go.Figure(data=[go.Bar(
            x=stage_labels,
            y=stage_values,
            marker_color=colors,
            text=stage_values,
            textposition="auto",
        )])
        fig_stages.update_layout(
            title="Records by Escalation Stage",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=350,
            margin=dict(t=50, b=30),
        )
        st.plotly_chart(fig_stages, use_container_width=True)

    with col_right:
        # Amount distribution pie chart
        if overdue_records:
            stage_amounts = {}
            for r in overdue_records:
                stage = get_escalation_stage(r.days_overdue, r.follow_up_count)
                stage_name = ESCALATION_MATRIX.get(stage, {}).get("stage_name", "Unknown")
                stage_amounts[stage_name] = stage_amounts.get(stage_name, 0) + r.amount_due

            fig_amount = go.Figure(data=[go.Pie(
                labels=list(stage_amounts.keys()),
                values=list(stage_amounts.values()),
                hole=0.4,
                marker_colors=colors[:len(stage_amounts)],
                textinfo="label+percent",
            )])
            fig_amount.update_layout(
                title="Outstanding Amount by Stage",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=350,
                margin=dict(t=50, b=30),
            )
            st.plotly_chart(fig_amount, use_container_width=True)
        else:
            st.info("No overdue records to display.")

    # Days overdue distribution
    if overdue_records:
        days_data = [{"Invoice": r.invoice_no, "Client": r.client_name, "Days Overdue": r.days_overdue, "Amount": r.amount_due} for r in overdue_records]
        df_days = pd.DataFrame(days_data)

        fig_days = px.bar(
            df_days,
            x="Invoice",
            y="Days Overdue",
            color="Days Overdue",
            color_continuous_scale=["#22c55e", "#eab308", "#f97316", "#ef4444"],
            hover_data=["Client", "Amount"],
            title="Days Overdue per Invoice",
        )
        fig_days.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=300,
        )
        st.plotly_chart(fig_days, use_container_width=True)


# ══════════════════════════════════════════════════════════
# TAB 2: Credit Records
# ══════════════════════════════════════════════════════════
with tab2:
    st.markdown("## 📋 Credit Records")

    # Convert to DataFrame for display
    records_data = []
    for r in records:
        stage = get_escalation_stage(r.days_overdue, r.follow_up_count)
        stage_name = ESCALATION_MATRIX.get(stage, {}).get("stage_name", "Not Overdue") if stage > 0 else "✅ Not Overdue"
        records_data.append({
            "Invoice": r.invoice_no,
            "Client": r.client_name,
            "Email": r.contact_email,
            "Amount": r.formatted_amount,
            "Due Date": str(r.due_date),
            "Days Overdue": r.days_overdue,
            "Follow-ups": r.follow_up_count,
            "Stage": stage_name,
        })

    df = pd.DataFrame(records_data)

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        filter_stage = st.multiselect("Filter by stage:", options=df["Stage"].unique().tolist())
    with col2:
        filter_overdue = st.checkbox("Show only overdue", value=False)

    if filter_stage:
        df = df[df["Stage"].isin(filter_stage)]
    if filter_overdue:
        df = df[df["Days Overdue"] > 0]

    st.dataframe(
        df,
        use_container_width=True,
        height=400,
        column_config={
            "Days Overdue": st.column_config.ProgressColumn(
                "Days Overdue",
                min_value=0,
                max_value=60,
                format="%d days",
            ),
        },
    )


# ══════════════════════════════════════════════════════════
# TAB 3: Run Agent
# ══════════════════════════════════════════════════════════
with tab3:
    st.markdown("## 🚀 Run the Agent")

    st.info(f"📧 **Current Mode:** `{EMAIL_MODE}` — {'Emails will be logged but NOT actually sent.' if EMAIL_MODE == 'dry_run' else '⚠️ LIVE MODE — Emails WILL be sent!'}")

    overdue = [r for r in records if r.days_overdue > 0]

    if not overdue:
        st.success("🎉 No overdue records! Nothing to process.")
    else:
        st.warning(f"📊 **{len(overdue)}** overdue records ready to process.")

        # Show preview
        with st.expander("📋 Preview records to process"):
            for r in overdue:
                stage = get_escalation_stage(r.days_overdue, r.follow_up_count)
                if stage == 5:
                    st.markdown(f"🚩 **{r.invoice_no}** — {r.client_name} — {r.formatted_amount} — **ESCALATION** ({r.days_overdue}d overdue)")
                else:
                    tone = ESCALATION_MATRIX[stage]["tone"]
                    st.markdown(f"📧 **{r.invoice_no}** — {r.client_name} — {r.formatted_amount} — Stage {stage} ({tone}) — {r.days_overdue}d overdue")

        if st.button("🚀 Run Agent Now", type="primary", use_container_width=True):
            with st.spinner("Running agent pipeline..."):
                try:
                    from src.agent import FinanceCreditAgent
                    agent = FinanceCreditAgent(data_file=data_file_path)
                    summary = agent.run()

                    st.success("✅ Agent run completed!")

                    # Display summary
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Emails Generated", summary.emails_generated)
                    col2.metric("Dry-Run", summary.emails_dry_run)
                    col3.metric("Sent", summary.emails_sent)
                    col4.metric("Escalated", summary.escalations_flagged)

                    if summary.errors:
                        st.error(f"⚠️ {len(summary.errors)} errors occurred:")
                        for err in summary.errors:
                            st.markdown(f"- {err}")

                    # Invalidate cache to refresh data
                    st.cache_data.clear()

                except Exception as e:
                    st.error(f"❌ Agent failed: {str(e)}")
                    st.exception(e)


# ══════════════════════════════════════════════════════════
# TAB 4: Email Preview
# ══════════════════════════════════════════════════════════
with tab4:
    st.markdown("## 📧 Email Preview")
    st.markdown("Preview generated emails from the latest agent run.")

    # Get latest audit logs
    logs = get_audit_logs(limit=20)

    if not logs:
        st.info("No emails generated yet. Run the agent first!")
    else:
        for log in logs:
            stage = log["escalation_stage"]
            status = log["send_status"]

            # Color-coded expander
            stage_emoji = ["", "🟢", "🟡", "🟠", "🔴", "🚩"][min(stage, 5)]
            status_emoji = {"sent": "✅", "dry_run": "📝", "failed": "❌", "escalated": "🚩", "skipped": "⏭️"}.get(status, "❓")

            with st.expander(
                f"{stage_emoji} {log['invoice_no']} — {log['client_name']} — "
                f"Stage {stage} — {status_emoji} {status.upper()}"
            ):
                col1, col2, col3 = st.columns(3)
                col1.markdown(f"**Amount:** ₹{log['amount_due']:,.0f}")
                col2.markdown(f"**Days Overdue:** {log['days_overdue']}")
                col3.markdown(f"**Tone:** {log['tone_used']}")

                st.markdown(f"**Subject:** {log['email_subject']}")
                st.divider()
                st.markdown(log["email_body"])

                if log.get("error_message"):
                    st.error(f"Error: {log['error_message']}")


# ══════════════════════════════════════════════════════════
# TAB 5: Audit Trail
# ══════════════════════════════════════════════════════════
with tab5:
    st.markdown("## 📋 Audit Trail")

    # Summary metrics
    audit_summary = get_audit_summary()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Logged", audit_summary.get("total_entries", 0))
    col2.metric("Sent", audit_summary.get("sent", 0))
    col3.metric("Dry-Run", audit_summary.get("dry_run", 0))
    col4.metric("Failed", audit_summary.get("failed", 0))
    col5.metric("Escalated", audit_summary.get("escalated", 0))

    st.divider()

    # Full audit log table
    logs = get_audit_logs(limit=100)
    if logs:
        df_logs = pd.DataFrame(logs)
        columns_to_show = [
            "id", "timestamp", "run_id", "invoice_no", "client_name",
            "amount_due", "days_overdue", "escalation_stage", "tone_used",
            "email_subject", "send_status",
        ]
        existing_cols = [c for c in columns_to_show if c in df_logs.columns]
        st.dataframe(df_logs[existing_cols], use_container_width=True, height=400)

        # Export button
        if st.button("📥 Export Audit Log to JSON"):
            export_path = export_audit_to_json()
            st.success(f"✅ Exported to: {export_path}")
    else:
        st.info("No audit entries yet. Run the agent to populate the audit trail.")


# ── Footer ────────────────────────────────────────────────
st.divider()
st.markdown(
    f"<div style='text-align: center; color: #6b7280; font-size: 0.8rem;'>"
    f"Finance Credit Follow-Up Email Agent v1.0.0 | "
    f"Built with LangChain + Google Gemini + Streamlit | "
    f"© 2025 {COMPANY_NAME}"
    f"</div>",
    unsafe_allow_html=True,
)
