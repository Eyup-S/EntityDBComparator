import json
import sys
import urllib.parse
from pathlib import Path

import pandas as pd
import streamlit as st

# ── page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Entity-DB Comparator",
    layout="wide",
)

STATUS_COLOR = {
    "CRITICAL":  "#e53935",
    "WARNING":   "#f57c00",
    "NOT_FOUND": "#757575",
    "OK":        "#2e7d32",
}
STATUS_EMOJI = {
    "CRITICAL":  "🔴",
    "WARNING":   "🟡",
    "NOT_FOUND": "⚫",
    "OK":        "🟢",
}

# ── helpers ────────────────────────────────────────────────────────────────────

def severity(s: str) -> int:
    return {"CRITICAL": 3, "WARNING": 2, "NOT_FOUND": 1}.get(s, 0)

def color_cell(val):
    """Used only for small per-entity tables."""
    c = STATUS_COLOR.get(val, "")
    return f"background-color:{c};color:white;font-weight:700" if c else ""

def with_emoji(series: pd.Series) -> pd.Series:
    """Vectorized: prepend status emoji. Fast on any size DataFrame."""
    return series.map(lambda s: STATUS_EMOJI.get(s, "") + " " + s)

def relative_path(file_path: str, project_root: str) -> str:
    if not project_root or not file_path:
        return file_path or "—"
    try:
        return str(Path(file_path).relative_to(project_root))
    except ValueError:
        return file_path

def idea_url(file_path: str, line: int = 1) -> str:
    encoded = urllib.parse.quote(file_path, safe="")
    return f"idea://open?file={encoded}&line={line}"

def is_blob_col(col: dict) -> bool:
    return col.get("isLob") and col.get("javaType", "").lower() in ("byte[]", "byte")

def is_clob_col(col: dict) -> bool:
    return col.get("isLob") and col.get("javaType", "").lower() in ("string", "charsequence")

# ── cached processing (runs once per unique report file) ───────────────────────

@st.cache_data(show_spinner="Processing report…")
def process_report(data: bytes):
    """
    All heavy work happens here and is cached.
    Returns everything needed to render the UI.
    """
    report = json.loads(data)
    entities = report.get("entities", [])

    # ── flat DataFrame for overview + issues tabs ──────────────────────────────
    rows = []
    for entity in entities:
        for col in entity.get("columns", []):
            oc = col.get("oracleColumn")  or {}
            pc = col.get("postgresColumn") or {}
            flags = []
            if col.get("isId"):         flags.append("PK")
            if col.get("isLob"):        flags.append("LOB")
            if col.get("isJoinColumn"): flags.append("FK")
            rows.append({
                "Entity":        entity["entityClass"].split(".")[-1],
                "Table":         entity["tableName"],
                "Java Field":    col["javaFieldName"],
                "Java Column":   col["javaColumnName"],
                "Java Type":     col["javaType"] + (" [" + ",".join(flags) + "]" if flags else ""),
                "Oracle Type":   oc.get("rawDataType", "—"),
                "Postgres Type": pc.get("rawDataType", "—"),
                "Oracle ✓":      col["oracleCompatibility"],
                "Postgres ✓":    col["postgresCompatibility"],
                "Status":        col["overallStatus"],
            })
    df = pd.DataFrame(rows) if rows else pd.DataFrame()

    # ── type distribution tables ───────────────────────────────────────────────
    all_cols = [col for e in entities for col in e.get("columns", [])]

    java_counts = (
        pd.Series([c["javaType"] for c in all_cols if c.get("javaType")])
        .value_counts().rename_axis("type").reset_index(name="count")
    )
    oracle_counts = (
        pd.Series([c["oracleColumn"]["dataType"] for c in all_cols
                   if c.get("oracleColumn") and c["oracleColumn"].get("dataType")])
        .value_counts().rename_axis("type").reset_index(name="count")
    )
    pg_counts = (
        pd.Series([c["postgresColumn"]["dataType"] for c in all_cols
                   if c.get("postgresColumn") and c["postgresColumn"].get("dataType")])
        .value_counts().rename_axis("type").reset_index(name="count")
    )

    # ── unique Java types for the filter widget ────────────────────────────────
    java_types = sorted({
        col["javaType"]
        for e in entities
        for col in e.get("columns", [])
        if col.get("javaType")
    })

    return report, df, java_counts, oracle_counts, pg_counts, java_types


# ── load ───────────────────────────────────────────────────────────────────────
st.title("Entity-DB Comparator")

default_path = sys.argv[1] if len(sys.argv) > 1 else None

with st.sidebar:
    st.header("📁 Report")
    if default_path and Path(default_path).exists():
        st.success(f"Loaded: `{Path(default_path).name}`")
        data = Path(default_path).read_bytes()
    else:
        uploaded = st.file_uploader("Load report.json", type="json")
        if not uploaded:
            st.info("Run the comparator first, then load report.json here.")
            st.stop()
        data = uploaded.read()

    report, df_all, java_counts, oracle_counts, pg_counts, all_java_types = process_report(data)
    entities_raw = report.get("entities", [])

    st.caption(f"Generated: {report.get('generatedAt', '—')}")
    st.divider()

    # ── project settings ───────────────────────────────────────────────────────
    st.subheader("⚙️ Project Settings")
    project_root = st.text_input(
        "Project root path",
        placeholder="/home/you/projects/my-app",
        help="Used to show relative file paths in entity cards.",
    ).strip()

    with st.expander("💡 IntelliJ setup (Ubuntu / Snap)", expanded=False):
        st.markdown(
            "Snap-installed IntelliJ does not register a browser URL handler automatically. "
            "Run these commands **once** on each Ubuntu machine to register `idea://`:"
        )
        st.code(
            """\
mkdir -p ~/.local/bin ~/.local/share/applications

# 1. Wrapper script
cat > ~/.local/bin/idea-url-handler.sh << 'EOF'
#!/bin/bash
URL="$1"
FILE=$(python3 -c "import sys,urllib.parse; u='$URL'; print(urllib.parse.unquote(u.split('file=')[1].split('&')[0]))")
LINE=$(python3 -c "u='$URL'; print(u.split('line=')[1] if 'line=' in u else '1')")
intellij-idea-ultimate --line "$LINE" "$FILE" &
EOF
chmod +x ~/.local/bin/idea-url-handler.sh

# 2. .desktop file
cat > ~/.local/share/applications/idea-url-handler.desktop << 'EOF'
[Desktop Entry]
Name=IntelliJ IDEA URL Handler
Exec=/home/$USER/.local/bin/idea-url-handler.sh %u
Terminal=false
Type=Application
MimeType=x-scheme-handler/idea;
EOF

# 3. Register idea:// with xdg
xdg-mime default idea-url-handler.desktop x-scheme-handler/idea
update-desktop-database ~/.local/share/applications/

# 4. Test
xdg-open "idea://open?file=$HOME/.bashrc&line=1"
""",
            language="bash",
        )
        st.caption(
            "After step 4, your browser will also handle `idea://` links. "
            "If Chrome/Firefox asks for permission the first time, click **Allow**."
        )

    st.divider()

    # ── filters ────────────────────────────────────────────────────────────────
    st.subheader("🔍 Filters")

    status_filter = st.multiselect(
        "Status",
        options=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
        default=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
    )
    java_type_filter = st.multiselect(
        "Java field types",
        options=all_java_types,
        default=[],
        placeholder="All types",
        help="Keep only entities that have at least one field of the selected type(s).",
    )

    st.markdown("**LOB field filter**")
    filter_blob = st.checkbox("Show only entities with BLOB fields")
    filter_clob = st.checkbox("Show only entities with CLOB fields")

    search = st.text_input("Search entity / field / column", "").strip().lower()
    show_ok_cols = st.checkbox("Show OK columns", value=True)

# ── filter entity list ─────────────────────────────────────────────────────────
entities = entities_raw

if java_type_filter:
    entities = [e for e in entities
                if any(c.get("javaType") in java_type_filter for c in e.get("columns", []))]
if filter_blob:
    entities = [e for e in entities if any(is_blob_col(c) for c in e.get("columns", []))]
if filter_clob:
    entities = [e for e in entities if any(is_clob_col(c) for c in e.get("columns", []))]

entity_names = {e["entityClass"].split(".")[-1] for e in entities}

# ── filter flat DataFrame ─────────────────────────────────────────────────────
def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df[df["Entity"].isin(entity_names)]
    df = df[df["Status"].isin(status_filter)]
    if not show_ok_cols:
        df = df[df["Status"] != "OK"]
    if search:
        mask = (
            df["Entity"].str.lower().str.contains(search, na=False)
            | df["Java Field"].str.lower().str.contains(search, na=False)
            | df["Java Column"].str.lower().str.contains(search, na=False)
            | df["Table"].str.lower().str.contains(search, na=False)
        )
        df = df[mask]
    return df

df_filtered = apply_filters(df_all)

# ── summary metrics ────────────────────────────────────────────────────────────
s = report["summary"]
m = st.columns(6)
m[0].metric("Entities",     s["totalEntities"])
m[1].metric("Columns",      s["totalColumns"])
m[2].metric("🔴 Critical",  s["criticalIssues"])
m[3].metric("🟡 Warnings",  s["warnings"])
m[4].metric("⚫ Not Found", s["notFound"])
m[5].metric("🟢 OK",        s["ok"])

# ── type distribution ──────────────────────────────────────────────────────────
with st.expander("📈 Type Distribution", expanded=False):
    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        st.markdown("**Java field types**")
        if not java_counts.empty:
            st.dataframe(java_counts, width="stretch", hide_index=True, height=280)
    with tc2:
        st.markdown("**Oracle column types**")
        if not oracle_counts.empty:
            st.dataframe(oracle_counts, width="stretch", hide_index=True, height=280)
        else:
            st.caption("No Oracle data")
    with tc3:
        st.markdown("**Postgres column types**")
        if not pg_counts.empty:
            st.dataframe(pg_counts, width="stretch", hide_index=True, height=280)
        else:
            st.caption("No Postgres data")

st.divider()

# ── tabs ───────────────────────────────────────────────────────────────────────
tab_overview, tab_entities, tab_issues = st.tabs(
    ["📊 Overview", "📋 By Entity", "⚠️ Issues Only"]
)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — Overview  (emoji mapping instead of styler — fast on any row count)
# ──────────────────────────────────────────────────────────────────────────────
with tab_overview:
    if not df_filtered.empty:
        display_cols = [
            "Entity", "Table",
            "Java Field", "Java Column", "Java Type",
            "Oracle Type", "Postgres Type",
            "Oracle ✓", "Postgres ✓", "Status",
        ]
        disp = df_filtered[display_cols].copy()
        disp["Oracle ✓"]  = with_emoji(disp["Oracle ✓"])
        disp["Postgres ✓"] = with_emoji(disp["Postgres ✓"])
        disp["Status"]    = with_emoji(disp["Status"])
        st.dataframe(disp, width="stretch", height=520, hide_index=True)
        st.caption(
            f"Showing {len(df_filtered)} column(s) across "
            f"{df_filtered['Entity'].nunique()} entity/entities"
        )
    else:
        st.info("No columns match the current filters.")

# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — Per-entity  (styler kept — each table is small)
# ──────────────────────────────────────────────────────────────────────────────
with tab_entities:
    sorted_entities = sorted(entities, key=lambda e: -severity(e["entityStatus"]))

    for entity in sorted_entities:
        estat = entity["entityStatus"]
        short_class = entity["entityClass"].split(".")[-1]
        label = f"{STATUS_EMOJI.get(estat, '')} **{short_class}**  —  `{entity['tableName']}`"

        entity_cols = [c for c in entity.get("columns", []) if c["overallStatus"] in status_filter]
        if not show_ok_cols:
            entity_cols = [c for c in entity_cols if c["overallStatus"] != "OK"]
        if search:
            entity_name_match = (
                search in entity["entityClass"].lower()
                or search in entity["tableName"].lower()
            )
            if not entity_name_match:
                entity_cols = [
                    c for c in entity_cols
                    if search in c["javaFieldName"].lower()
                    or search in c["javaColumnName"].lower()
                ]
            if not entity_cols:
                continue
        if java_type_filter and not any(
            c.get("javaType") in java_type_filter for c in entity.get("columns", [])
        ):
            continue

        with st.expander(label, expanded=(estat in ("CRITICAL", "WARNING"))):

            h1, h2 = st.columns([5, 1])
            with h1:
                rel = relative_path(entity.get("filePath", ""), project_root)
                st.markdown(f"📄 `{rel}`", help=entity.get("filePath") or "")
            with h2:
                file_path = entity.get("filePath")
                if file_path:
                    st.link_button(
                        "💡 Open in IDEA",
                        url=idea_url(file_path),
                        help=f"Opens via idea:// handler → {file_path}",
                    )

            db1, db2 = st.columns(2)
            with db1:
                icon = "✅" if entity["oracleTableFound"] else "❌"
                st.markdown(f"Oracle table: {icon} {'found' if entity['oracleTableFound'] else '**NOT FOUND**'}")
            with db2:
                icon = "✅" if entity["postgresTableFound"] else "❌"
                st.markdown(f"Postgres table: {icon} {'found' if entity['postgresTableFound'] else '**NOT FOUND**'}")

            if entity_cols:
                col_rows = []
                for col in entity_cols:
                    oc = col.get("oracleColumn")  or {}
                    pc = col.get("postgresColumn") or {}
                    flags = []
                    if col.get("isId"):         flags.append("PK")
                    if col.get("isLob"):        flags.append("LOB")
                    if col.get("isJoinColumn"): flags.append("FK")
                    col_rows.append({
                        "Field":      col["javaFieldName"],
                        "Column":     col["javaColumnName"],
                        "Java Type":  col["javaType"] + (" [" + ",".join(flags) + "]" if flags else ""),
                        "Oracle":     oc.get("rawDataType", "—"),
                        "Postgres":   pc.get("rawDataType", "—"),
                        "Oracle ✓":   col["oracleCompatibility"],
                        "Postgres ✓": col["postgresCompatibility"],
                        "Status":     col["overallStatus"],
                    })
                cdf = pd.DataFrame(col_rows)
                st.dataframe(
                    cdf.style.map(color_cell, subset=["Oracle ✓", "Postgres ✓", "Status"]),
                    width="stretch",
                    hide_index=True,
                )

            issues = [i for col in entity_cols for i in (col.get("issues") or [])]
            if issues:
                st.markdown("**Issues:**")
                for issue in issues:
                    lvl = "🔴" if any(w in issue for w in ("coerces", "reject", "CRITICAL")) else "🟡"
                    st.markdown(f"{lvl} {issue}")

            unmapped_o = entity.get("unmappedOracleColumns") or []
            unmapped_p = entity.get("unmappedPostgresColumns") or []
            if unmapped_o or unmapped_p:
                st.markdown("**DB columns with no entity mapping:**")
                u1, u2 = st.columns(2)
                with u1:
                    if unmapped_o:
                        st.markdown("Oracle: " + ", ".join(f"`{c}`" for c in unmapped_o))
                with u2:
                    if unmapped_p:
                        st.markdown("Postgres: " + ", ".join(f"`{c}`" for c in unmapped_p))

# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — Issues only  (emoji mapping — can be large)
# ──────────────────────────────────────────────────────────────────────────────
with tab_issues:
    issue_rows = []
    for entity in entities:
        for col in entity.get("columns", []):
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
                idf["Entity"].str.lower().str.contains(search, na=False)
                | idf["Field"].str.lower().str.contains(search, na=False)
                | idf["Issue"].str.lower().str.contains(search, na=False)
            ]
        idf = idf.sort_values("Status", key=lambda s: s.map(severity), ascending=False)
        idf["Status"] = with_emoji(idf["Status"])
        st.dataframe(idf, width="stretch", height=520, hide_index=True)
        st.caption(f"{len(idf)} issue(s)")
    else:
        st.success("No issues match the current filters.")
