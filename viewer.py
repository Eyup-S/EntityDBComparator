import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Entity-DB Comparator",
    page_icon="🔍",
    layout="wide",
)

STATUS_COLOR = {
    "CRITICAL":  "#ff4b4b",
    "WARNING":   "#ffa500",
    "NOT_FOUND": "#888888",
    "OK":        "#21c354",
}

STATUS_EMOJI = {
    "CRITICAL":  "🔴",
    "WARNING":   "🟡",
    "NOT_FOUND": "⚫",
    "OK":        "🟢",
}

# ── helpers ───────────────────────────────────────────────────────────────────

def badge(status: str) -> str:
    color = STATUS_COLOR.get(status, "#888")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.78em;font-weight:600">{status}</span>'


def load_report(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def severity(s: str) -> int:
    return {"CRITICAL": 3, "WARNING": 2, "NOT_FOUND": 1, "OK": 0}.get(s, 0)


# ── load ──────────────────────────────────────────────────────────────────────

st.title("🔍 Entity-DB Comparator")

# Accept a path from CLI arg or let the user upload
default_path = sys.argv[1] if len(sys.argv) > 1 else None

with st.sidebar:
    st.header("Report")
    if default_path and Path(default_path).exists():
        st.success(f"Loaded: `{Path(default_path).name}`")
        report = load_report(default_path)
    else:
        uploaded = st.file_uploader("Load report.json", type="json")
        if not uploaded:
            st.info("Run the comparator first, then load the report.json here.")
            st.stop()
        report = json.load(uploaded)

    st.divider()
    st.caption(f"Generated: {report.get('generatedAt', '—')}")

    # ── filters ───────────────────────────────────────────────────────────────
    st.subheader("Filters")
    status_filter = st.multiselect(
        "Show statuses",
        options=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
        default=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
    )
    search = st.text_input("Search entity / field / column", "").strip().lower()
    show_ok_cols = st.checkbox("Show OK columns", value=True)

summary = report["summary"]
entities = report["entities"]

# ── summary cards ─────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Entities",  summary["totalEntities"])
c2.metric("Columns",   summary["totalColumns"])
c3.metric("🔴 Critical",  summary["criticalIssues"])
c4.metric("🟡 Warnings",  summary["warnings"])
c5.metric("⚫ Not Found", summary["notFound"])
c6.metric("🟢 OK",         summary["ok"])

st.divider()

# ── flatten all columns into a dataframe for the overview table ───────────────
rows = []
for entity in entities:
    for col in entity["columns"]:
        oracle_col  = col.get("oracleColumn")  or {}
        pg_col      = col.get("postgresColumn") or {}
        rows.append({
            "Entity":          entity["entityClass"].split(".")[-1],
            "Table":           entity["tableName"],
            "Java Field":      col["javaFieldName"],
            "Java Column":     col["javaColumnName"],
            "Java Type":       col["javaType"],
            "Oracle Type":     oracle_col.get("rawDataType", "—"),
            "Postgres Type":   pg_col.get("rawDataType", "—"),
            "Oracle ✓":        col["oracleCompatibility"],
            "Postgres ✓":      col["postgresCompatibility"],
            "Status":          col["overallStatus"],
            "Issues":          "\n".join(col.get("issues") or []),
            "_entity_status":  entity["entityStatus"],
            "_entity_class":   entity["entityClass"],
        })

df_all = pd.DataFrame(rows)

# ── apply filters ─────────────────────────────────────────────────────────────
df = df_all[df_all["Status"].isin(status_filter)]
if not show_ok_cols:
    df = df[df["Status"] != "OK"]
if search:
    mask = (
        df["Entity"].str.lower().str.contains(search) |
        df["Java Field"].str.lower().str.contains(search) |
        df["Java Column"].str.lower().str.contains(search) |
        df["Table"].str.lower().str.contains(search)
    )
    df = df[mask]

# ── tabs ──────────────────────────────────────────────────────────────────────
tab_overview, tab_entities, tab_issues = st.tabs(["📊 Overview", "📋 By Entity", "⚠️ Issues Only"])

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — Overview table
# ──────────────────────────────────────────────────────────────────────────────
with tab_overview:
    display_cols = ["Entity", "Table", "Java Field", "Java Column", "Java Type",
                    "Oracle Type", "Postgres Type", "Oracle ✓", "Postgres ✓", "Status"]

    def color_status(val):
        color = STATUS_COLOR.get(val, "")
        return f"background-color:{color};color:white;font-weight:600" if color else ""

    styled = (
        df[display_cols]
        .style
        .map(color_status, subset=["Oracle ✓", "Postgres ✓", "Status"])
    )

    st.dataframe(styled, use_container_width=True, height=500)
    st.caption(f"Showing {len(df)} column(s)")

# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — Per-entity detail
# ──────────────────────────────────────────────────────────────────────────────
with tab_entities:
    # Sort entities: worst status first
    sorted_entities = sorted(entities, key=lambda e: -severity(e["entityStatus"]))

    for entity in sorted_entities:
        estat = entity["entityStatus"]
        emoji = STATUS_EMOJI.get(estat, "")
        label = f"{emoji} **{entity['entityClass'].split('.')[-1]}**  —  `{entity['tableName']}`"

        # Only show entities that contain at least one column matching active filters
        entity_cols = [c for c in entity["columns"] if c["overallStatus"] in status_filter]
        if not show_ok_cols:
            entity_cols = [c for c in entity_cols if c["overallStatus"] != "OK"]
        if search:
            entity_name_match = (
                search in entity["entityClass"].lower() or
                search in entity["tableName"].lower()
            )
            if not entity_name_match:
                entity_cols = [
                    c for c in entity_cols if (
                        search in c["javaFieldName"].lower() or
                        search in c["javaColumnName"].lower()
                    )
                ]
        if not entity_cols and search:
            continue

        with st.expander(label, expanded=(estat in ("CRITICAL", "WARNING"))):
            # Table found badges
            db_cols = st.columns(2)
            with db_cols[0]:
                oracle_ok = entity["oracleTableFound"]
                st.markdown(
                    f"Oracle: {'✅ found' if oracle_ok else '❌ **table not found**'}",
                    unsafe_allow_html=True,
                )
            with db_cols[1]:
                pg_ok = entity["postgresTableFound"]
                st.markdown(
                    f"Postgres: {'✅ found' if pg_ok else '❌ **table not found**'}",
                    unsafe_allow_html=True,
                )

            # Column table
            col_rows = []
            for col in entity_cols:
                oracle_col = col.get("oracleColumn") or {}
                pg_col     = col.get("postgresColumn") or {}
                flags = []
                if col.get("isId"):         flags.append("PK")
                if col.get("isLob"):        flags.append("LOB")
                if col.get("isJoinColumn"): flags.append("FK")
                col_rows.append({
                    "Field":         col["javaFieldName"],
                    "Column":        col["javaColumnName"],
                    "Java Type":     col["javaType"] + (" [" + ",".join(flags) + "]" if flags else ""),
                    "Oracle":        oracle_col.get("rawDataType", "—"),
                    "Postgres":      pg_col.get("rawDataType", "—"),
                    "Oracle ✓":      col["oracleCompatibility"],
                    "Postgres ✓":    col["postgresCompatibility"],
                    "Status":        col["overallStatus"],
                })

            if col_rows:
                cdf = pd.DataFrame(col_rows)

                def color_cell(val):
                    c = STATUS_COLOR.get(val, "")
                    return f"background-color:{c};color:white;font-weight:600" if c else ""

                st.dataframe(
                    cdf.style.map(color_cell, subset=["Oracle ✓", "Postgres ✓", "Status"]),
                    use_container_width=True,
                    hide_index=True,
                )

            # Issues
            issues = [
                issue
                for col in entity_cols
                for issue in (col.get("issues") or [])
            ]
            if issues:
                st.markdown("**Issues:**")
                for issue in issues:
                    lvl = "🔴" if "CRITICAL" in issue or "Oracle coerces" in issue else "🟡"
                    st.markdown(f"{lvl} {issue}")

            # Unmapped DB columns
            unmapped_oracle = entity.get("unmappedOracleColumns") or []
            unmapped_pg     = entity.get("unmappedPostgresColumns") or []
            if unmapped_oracle or unmapped_pg:
                st.markdown("**Columns in DB with no entity mapping:**")
                uc1, uc2 = st.columns(2)
                with uc1:
                    if unmapped_oracle:
                        st.markdown("*Oracle:* " + ", ".join(f"`{c}`" for c in unmapped_oracle))
                with uc2:
                    if unmapped_pg:
                        st.markdown("*Postgres:* " + ", ".join(f"`{c}`" for c in unmapped_pg))

# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — Issues only
# ──────────────────────────────────────────────────────────────────────────────
with tab_issues:
    issue_rows = []
    for entity in entities:
        for col in entity["columns"]:
            for issue in (col.get("issues") or []):
                issue_rows.append({
                    "Status":    col["overallStatus"],
                    "Entity":    entity["entityClass"].split(".")[-1],
                    "Table":     entity["tableName"],
                    "Field":     col["javaFieldName"],
                    "Java Type": col["javaType"],
                    "Issue":     issue,
                })

    if issue_rows:
        idf = pd.DataFrame(issue_rows)
        idf = idf[idf["Status"].isin(status_filter)]
        if search:
            idf = idf[
                idf["Entity"].str.lower().str.contains(search) |
                idf["Field"].str.lower().str.contains(search) |
                idf["Issue"].str.lower().str.contains(search)
            ]
        idf_sorted = idf.sort_values("Status", key=lambda s: s.map(severity), ascending=False)

        def color_status_col(val):
            c = STATUS_COLOR.get(val, "")
            return f"background-color:{c};color:white;font-weight:600" if c else ""

        st.dataframe(
            idf_sorted.style.map(color_status_col, subset=["Status"]),
            use_container_width=True,
            height=500,
            hide_index=True,
        )
        st.caption(f"{len(idf_sorted)} issue(s)")
    else:
        st.success("No issues found matching current filters.")
