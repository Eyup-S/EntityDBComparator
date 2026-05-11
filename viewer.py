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

STATUS_EMOJI = {
    "CRITICAL":  "🔴",
    "WARNING":   "🟡",
    "NOT_FOUND": "⚫",
    "OK":        "🟢",
}

# ── helpers ────────────────────────────────────────────────────────────────────

def severity(s: str) -> int:
    return {"CRITICAL": 3, "WARNING": 2, "NOT_FOUND": 1}.get(s, 0)

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

def render_entity_detail(entity, project_root, status_filter, show_ok_cols, show_header=True):
    """Render entity detail card — used inline when a table row is selected."""
    estat = entity["entityStatus"]
    short_class = entity["entityClass"].split(".")[-1]
    if show_header:
        st.markdown(
            f"{STATUS_EMOJI.get(estat, '')} **{short_class}** — `{entity['tableName']}`"
        )

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

    ora_schema = entity.get("oracleSchemaName") or ""
    pg_schema  = entity.get("postgresSchemaName") or ""
    db1, db2 = st.columns(2)
    with db1:
        icon = "✅" if entity["oracleTableFound"] else "❌"
        schema_hint = f"  `{ora_schema}.{entity['tableName']}`" if ora_schema else ""
        st.markdown(f"Oracle table: {icon} {'found' if entity['oracleTableFound'] else '**NOT FOUND**'}{schema_hint}")
    with db2:
        icon = "✅" if entity["postgresTableFound"] else "❌"
        schema_hint = f"  `{pg_schema}.{entity['tableName']}`" if pg_schema else ""
        st.markdown(f"Postgres table: {icon} {'found' if entity['postgresTableFound'] else '**NOT FOUND**'}{schema_hint}")

    entity_cols = [c for c in entity.get("columns", []) if c["overallStatus"] in status_filter]
    if not show_ok_cols:
        entity_cols = [c for c in entity_cols if c["overallStatus"] != "OK"]

    if entity_cols:
        col_rows = []
        for col in entity_cols:
            oc = col.get("oracleColumn") or {}
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
        cdf["Oracle ✓"]   = with_emoji(cdf["Oracle ✓"])
        cdf["Postgres ✓"] = with_emoji(cdf["Postgres ✓"])
        cdf["Status"]     = with_emoji(cdf["Status"])
        st.dataframe(cdf, width="stretch", hide_index=True)

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
            ora_schema = entity.get("oracleSchemaName") or ""
            pg_schema  = entity.get("postgresSchemaName") or ""
            schema     = ora_schema or pg_schema
            table_disp = f"{schema}.{entity['tableName']}" if schema else entity["tableName"]
            rows.append({
                "Entity":        entity["entityClass"].split(".")[-1],
                "Table":         table_disp,
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

    st.markdown("**LOB field filter**")
    filter_blob = st.checkbox("Show only entities with BLOB fields")
    filter_clob = st.checkbox("Show only entities with CLOB fields")

    search = st.text_input("Search entity / field / column", "").strip().lower()
    show_ok_cols = st.checkbox("Show OK columns", value=True)

# ── filter entity list (LOB only — status/java_type are per-tab) ──────────────
entities = entities_raw

if filter_blob:
    entities = [e for e in entities if any(is_blob_col(c) for c in e.get("columns", []))]
if filter_clob:
    entities = [e for e in entities if any(is_clob_col(c) for c in e.get("columns", []))]

entity_names = {e["entityClass"].split(".")[-1] for e in entities}

# ── base DataFrame filter (LOB entity scope + search + show_ok_cols) ──────────
def apply_base_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df[df["Entity"].isin(entity_names)]
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

df_base = apply_base_filters(df_all)

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
# TAB 1 — Overview  (emoji mapping + pagination)
# ──────────────────────────────────────────────────────────────────────────────
with tab_overview:
    # ── filter row ────────────────────────────────────────────────────────────
    of1, of2, of3, of4 = st.columns(4)
    with of1:
        ov_status = st.multiselect(
            "Overall Status", ["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
            default=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
            key="ov_status",
        )
    with of2:
        ov_oracle = st.multiselect(
            "Oracle ✓", ["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
            default=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
            key="ov_oracle",
        )
    with of3:
        ov_pg = st.multiselect(
            "Postgres ✓", ["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
            default=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
            key="ov_pg",
        )
    with of4:
        ov_java_type = st.multiselect(
            "Java Type", all_java_types,
            default=[], placeholder="All types",
            key="ov_java_type",
        )

    # ── search + page size ────────────────────────────────────────────────────
    ov_col1, ov_col2 = st.columns([5, 1])
    with ov_col1:
        ov_search = st.text_input(
            "Search",
            placeholder="Entity name, table, field, column…",
            label_visibility="collapsed",
            key="ov_search",
        ).strip().lower()
    with ov_col2:
        page_size = st.selectbox(
            "Rows", options=[50, 100, 200, 500],
            index=1, label_visibility="collapsed", key="ov_page_size",
        )

    # ── apply filters ─────────────────────────────────────────────────────────
    df_ov = df_base.copy()
    df_ov = df_ov[df_ov["Status"].isin(ov_status)]
    df_ov = df_ov[df_ov["Oracle ✓"].isin(ov_oracle)]
    df_ov = df_ov[df_ov["Postgres ✓"].isin(ov_pg)]
    if ov_java_type:
        df_ov = df_ov[df_ov["Java Type"].str.split(" [").str[0].isin(ov_java_type)]
    if ov_search:
        mask = (
            df_ov["Entity"].str.lower().str.contains(ov_search, na=False)
            | df_ov["Table"].str.lower().str.contains(ov_search, na=False)
            | df_ov["Java Field"].str.lower().str.contains(ov_search, na=False)
            | df_ov["Java Column"].str.lower().str.contains(ov_search, na=False)
            | df_ov["Java Type"].str.lower().str.contains(ov_search, na=False)
        )
        df_ov = df_ov[mask]

    # ── auto-reset page when filters change ───────────────────────────────────
    filter_fingerprint = (
        tuple(sorted(ov_status)), tuple(sorted(ov_oracle)), tuple(sorted(ov_pg)),
        tuple(sorted(ov_java_type)),
        filter_blob, filter_clob, search, show_ok_cols,
        ov_search, page_size,
    )
    if st.session_state.get("_ov_fp") != filter_fingerprint:
        st.session_state["_ov_fp"] = filter_fingerprint
        st.session_state["ov_page"] = 0

    # ── pagination ────────────────────────────────────────────────────────────
    total_rows  = len(df_ov)
    total_pages = max(1, -(-total_rows // page_size))
    page        = min(st.session_state.get("ov_page", 0), total_pages - 1)

    start = page * page_size
    end   = start + page_size
    df_page = df_ov.iloc[start:end]

    # ── render table ──────────────────────────────────────────────────────────
    if not df_page.empty:
        display_cols = [
            "Entity", "Table",
            "Java Field", "Java Column", "Java Type",
            "Oracle Type", "Postgres Type",
            "Oracle ✓", "Postgres ✓", "Status",
        ]
        disp = df_page[display_cols].copy()
        disp["Oracle ✓"]   = with_emoji(disp["Oracle ✓"])
        disp["Postgres ✓"] = with_emoji(disp["Postgres ✓"])
        disp["Status"]     = with_emoji(disp["Status"])
        ov_evt = st.dataframe(
            disp, width="stretch", height=520, hide_index=True,
            on_select="rerun", selection_mode="single-row", key="ov_table",
        )
        if ov_evt.selection.rows:
            sel_entity = disp.iloc[ov_evt.selection.rows[0]]["Entity"]
            found = next(
                (e for e in entities_raw if e["entityClass"].split(".")[-1] == sel_entity),
                None,
            )
            if found:
                with st.container(border=True):
                    render_entity_detail(found, project_root, ov_status, show_ok_cols)
    else:
        st.info("No columns match the current filters.")

    # ── pagination controls ───────────────────────────────────────────────────
    pc1, pc2, pc3, pc4, pc5 = st.columns([1, 1, 3, 1, 1])
    with pc1:
        if st.button("⏮ First", disabled=(page == 0), use_container_width=True):
            st.session_state["ov_page"] = 0
            st.rerun()
    with pc2:
        if st.button("◀ Prev", disabled=(page == 0), use_container_width=True):
            st.session_state["ov_page"] = page - 1
            st.rerun()
    with pc3:
        st.caption(
            f"Page **{page + 1}** of **{total_pages}** "
            f"— rows {start + 1}–{min(end, total_rows)} of **{total_rows}**"
            + (f" (filtered from {len(df_all)} total)" if total_rows != len(df_all) else "")
        )
    with pc4:
        if st.button("Next ▶", disabled=(page >= total_pages - 1), use_container_width=True):
            st.session_state["ov_page"] = page + 1
            st.rerun()
    with pc5:
        if st.button("Last ⏭", disabled=(page >= total_pages - 1), use_container_width=True):
            st.session_state["ov_page"] = total_pages - 1
            st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — Per-entity  (paginated — only renders current page of expanders)
# ──────────────────────────────────────────────────────────────────────────────
with tab_entities:
    # ── filter row ────────────────────────────────────────────────────────────
    ef1, ef2, ef3 = st.columns([2, 3, 1])
    with ef1:
        ent_status = st.multiselect(
            "Status", ["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
            default=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
            key="ent_status",
        )
    with ef2:
        ent_java_type = st.multiselect(
            "Java Type", all_java_types,
            default=[], placeholder="All types",
            key="ent_java_type",
        )
    with ef3:
        ent_page_size = st.selectbox(
            "Per page", options=[10, 25, 50],
            index=1, key="ent_page_size",
        )

    # ── pre-filter entity list ─────────────────────────────────────────────
    def _entity_visible(entity):
        if not any(c["overallStatus"] in ent_status for c in entity.get("columns", [])):
            return False
        if ent_java_type and not any(
            c.get("javaType") in ent_java_type for c in entity.get("columns", [])
        ):
            return False
        if search:
            if search in entity["entityClass"].lower() or search in entity["tableName"].lower():
                return True
            status_cols = [
                c for c in entity.get("columns", [])
                if c["overallStatus"] in ent_status
                and (show_ok_cols or c["overallStatus"] != "OK")
            ]
            return any(
                search in c["javaFieldName"].lower() or search in c["javaColumnName"].lower()
                for c in status_cols
            )
        return True

    sorted_entities  = sorted(entities, key=lambda e: -severity(e["entityStatus"]))
    visible_entities = [e for e in sorted_entities if _entity_visible(e)]

    # ── auto-reset page ───────────────────────────────────────────────────────
    ent_fp = (
        tuple(sorted(ent_status)), tuple(sorted(ent_java_type)),
        filter_blob, filter_clob, search, show_ok_cols, ent_page_size,
    )
    if st.session_state.get("_ent_fp") != ent_fp:
        st.session_state["_ent_fp"] = ent_fp
        st.session_state["ent_page"] = 0

    ent_total  = len(visible_entities)
    ent_pages  = max(1, -(-ent_total // ent_page_size))
    ent_page   = min(st.session_state.get("ent_page", 0), ent_pages - 1)
    ent_start  = ent_page * ent_page_size
    ent_end    = ent_start + ent_page_size

    # ── pagination controls (top) ─────────────────────────────────────────────
    ep1, ep2, ep3, ep4, ep5 = st.columns([1, 1, 3, 1, 1])
    with ep1:
        if st.button("⏮ First", disabled=(ent_page == 0), use_container_width=True, key="ent_first"):
            st.session_state["ent_page"] = 0; st.rerun()
    with ep2:
        if st.button("◀ Prev", disabled=(ent_page == 0), use_container_width=True, key="ent_prev"):
            st.session_state["ent_page"] = ent_page - 1; st.rerun()
    with ep3:
        st.caption(
            f"Page **{ent_page + 1}** of **{ent_pages}** "
            f"— entities {ent_start + 1}–{min(ent_end, ent_total)} of **{ent_total}**"
        )
    with ep4:
        if st.button("Next ▶", disabled=(ent_page >= ent_pages - 1), use_container_width=True, key="ent_next"):
            st.session_state["ent_page"] = ent_page + 1; st.rerun()
    with ep5:
        if st.button("Last ⏭", disabled=(ent_page >= ent_pages - 1), use_container_width=True, key="ent_last"):
            st.session_state["ent_page"] = ent_pages - 1; st.rerun()

    # ── render only current page ──────────────────────────────────────────────
    for entity in visible_entities[ent_start:ent_end]:
        estat       = entity["entityStatus"]
        short_class = entity["entityClass"].split(".")[-1]
        schema      = entity.get("oracleSchemaName") or entity.get("postgresSchemaName") or ""
        table_disp  = f"{schema}.{entity['tableName']}" if schema else entity["tableName"]
        label       = f"{STATUS_EMOJI.get(estat, '')} **{short_class}**  —  `{table_disp}`"
        with st.expander(label, expanded=False):
            render_entity_detail(entity, project_root, ent_status, show_ok_cols, show_header=False)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — Issues only  (emoji mapping + pagination)
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

    if not issue_rows:
        st.success("No issues match the current filters.")
    else:
        idf_all = pd.DataFrame(issue_rows)

        # ── filter row ────────────────────────────────────────────────────────
        isf1, isf2 = st.columns([4, 1])
        with isf1:
            is_status = st.multiselect(
                "Status", ["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
                default=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
                key="is_status_filter",
            )
        with isf2:
            is_page_size = st.selectbox(
                "Per page", options=[50, 100, 200, 500],
                index=1, key="is_page_size",
            )

        idf_all = idf_all[idf_all["Status"].isin(is_status)]
        if search:
            idf_all = idf_all[
                idf_all["Entity"].str.lower().str.contains(search, na=False)
                | idf_all["Field"].str.lower().str.contains(search, na=False)
                | idf_all["Issue"].str.lower().str.contains(search, na=False)
            ]
        idf_all = idf_all.sort_values("Status", key=lambda s: s.map(severity), ascending=False)

        # ── auto-reset page when filters change ───────────────────────────────
        is_fp = (
            tuple(sorted(is_status)),
            filter_blob, filter_clob,
            search, show_ok_cols,
            is_page_size,
        )
        if st.session_state.get("_is_fp") != is_fp:
            st.session_state["_is_fp"] = is_fp
            st.session_state["is_page"] = 0

        # ── pagination ────────────────────────────────────────────────────────
        is_total = len(idf_all)
        is_pages = max(1, -(-is_total // is_page_size))
        is_page  = min(st.session_state.get("is_page", 0), is_pages - 1)
        is_start = is_page * is_page_size
        is_end   = is_start + is_page_size
        idf_page = idf_all.iloc[is_start:is_end].copy()
        idf_page["Status"] = with_emoji(idf_page["Status"])

        # ── render table ──────────────────────────────────────────────────────
        is_evt = st.dataframe(
            idf_page, width="stretch", height=520, hide_index=True,
            on_select="rerun", selection_mode="single-row", key="is_table",
        )
        if is_evt.selection.rows:
            sel_entity = idf_page.iloc[is_evt.selection.rows[0]]["Entity"]
            found = next(
                (e for e in entities_raw if e["entityClass"].split(".")[-1] == sel_entity),
                None,
            )
            if found:
                with st.container(border=True):
                    render_entity_detail(found, project_root, is_status, show_ok_cols)

        # ── pagination controls ───────────────────────────────────────────────
        ic1, ic2, ic3, ic4, ic5 = st.columns([1, 1, 3, 1, 1])
        with ic1:
            if st.button("⏮ First", disabled=(is_page == 0), use_container_width=True, key="is_first"):
                st.session_state["is_page"] = 0
                st.rerun()
        with ic2:
            if st.button("◀ Prev", disabled=(is_page == 0), use_container_width=True, key="is_prev"):
                st.session_state["is_page"] = is_page - 1
                st.rerun()
        with ic3:
            st.caption(
                f"Page **{is_page + 1}** of **{is_pages}** "
                f"— rows {is_start + 1}–{min(is_end, is_total)} of **{is_total}** issue(s)"
            )
        with ic4:
            if st.button("Next ▶", disabled=(is_page >= is_pages - 1), use_container_width=True, key="is_next"):
                st.session_state["is_page"] = is_page + 1
                st.rerun()
        with ic5:
            if st.button("Last ⏭", disabled=(is_page >= is_pages - 1), use_container_width=True, key="is_last"):
                st.session_state["is_page"] = is_pages - 1
                st.rerun()
