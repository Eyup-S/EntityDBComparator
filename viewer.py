import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# ── page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Entity-DB Comparator",
    page_icon="🔍",
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

def badge(status: str) -> str:
    c = STATUS_COLOR.get(status, "#888")
    return (
        f'<span style="background:{c};color:#fff;padding:2px 9px;'
        f'border-radius:4px;font-size:0.78em;font-weight:700">{status}</span>'
    )

def severity(s: str) -> int:
    return {"CRITICAL": 3, "WARNING": 2, "NOT_FOUND": 1}.get(s, 0)

def color_cell(val):
    c = STATUS_COLOR.get(val, "")
    return f"background-color:{c};color:white;font-weight:700" if c else ""

def load_report(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def relative_path(file_path: str, project_root: str) -> str:
    if not project_root or not file_path:
        return file_path or "—"
    try:
        return str(Path(file_path).relative_to(project_root))
    except ValueError:
        return file_path

def get_module(file_path: str, project_root: str, module_index: int) -> str:
    """Split the path relative to project root and take segment at module_index."""
    if not file_path:
        return "unknown"
    rel = relative_path(file_path, project_root) if project_root else file_path
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if module_index < len(parts):
        return parts[module_index]
    return parts[0] if parts else "unknown"

def open_intellij(file_path: str, idea_exe: str | None):
    """Launch IntelliJ IDEA with the given file. Fire-and-forget."""
    if not file_path or not Path(file_path).exists():
        st.toast(f"File not found: {file_path}", icon="❌")
        return
    try:
        if idea_exe and Path(idea_exe).exists():
            subprocess.Popen([idea_exe, file_path])
        elif shutil.which("idea"):
            subprocess.Popen(["idea", file_path])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-a", "IntelliJ IDEA", file_path])
        elif platform.system() == "Windows":
            for candidate in [
                r"C:\Program Files\JetBrains\IntelliJ IDEA\bin\idea64.exe",
                r"C:\Program Files\JetBrains\IntelliJ IDEA Community Edition\bin\idea64.exe",
            ]:
                if Path(candidate).exists():
                    subprocess.Popen([candidate, file_path])
                    return
            st.toast("IntelliJ IDEA not found. Set the path in ⚙️ Settings.", icon="❌")
        else:
            subprocess.Popen(["idea.sh", file_path])
        st.toast(f"Opening {Path(file_path).name} in IntelliJ…", icon="💡")
    except Exception as exc:
        st.toast(f"Could not open IntelliJ: {exc}", icon="❌")

# ── LOB detection ──────────────────────────────────────────────────────────────

def is_blob_col(col: dict) -> bool:
    return col.get("isLob") and col.get("javaType", "").lower() in ("byte[]", "byte")

def is_clob_col(col: dict) -> bool:
    return col.get("isLob") and col.get("javaType", "").lower() in ("string", "charsequence")

# ── load ───────────────────────────────────────────────────────────────────────
st.title("🔍 Entity-DB Comparator")

default_path = sys.argv[1] if len(sys.argv) > 1 else None

with st.sidebar:
    st.header("📁 Report")
    if default_path and Path(default_path).exists():
        st.success(f"Loaded: `{Path(default_path).name}`")
        report = load_report(default_path)
    else:
        uploaded = st.file_uploader("Load report.json", type="json")
        if not uploaded:
            st.info("Run the comparator first, then load report.json here.")
            st.stop()
        report = json.load(uploaded)

    st.caption(f"Generated: {report.get('generatedAt', '—')}")
    st.divider()

    # ── project settings ───────────────────────────────────────────────────────
    st.subheader("⚙️ Project Settings")
    project_root = st.text_input(
        "Project root path",
        placeholder="/Users/you/projects/my-app",
        help="Used to compute relative file paths and module names.",
    ).strip()

    # Show a path preview so the user can figure out the right index
    sample_path = None
    for e in report.get("entities", []):
        if e.get("filePath"):
            sample_path = e["filePath"]
            break

    module_index = st.number_input(
        "Module segment index (in relative path)",
        min_value=0, max_value=20, value=0, step=1,
        help="After stripping the project root, split by '/' and take this index as the module name. 0 = first segment.",
    )

    if sample_path:
        rel = relative_path(sample_path, project_root)
        parts = [p for p in rel.replace("\\", "/").split("/") if p]
        idx = min(int(module_index), len(parts) - 1) if parts else 0
        preview_module = parts[idx] if parts else "—"
        st.caption(f"Sample: `{rel}`\n\nModule → **`{preview_module}`**")

    idea_exe = st.text_input(
        "IntelliJ executable (optional)",
        placeholder="/Applications/IntelliJ IDEA.app/Contents/MacOS/idea",
        help="Leave blank to auto-detect.",
    ).strip() or None

    st.divider()

    # ── build enriched entity list with module + relative path ─────────────────
    entities_raw = report.get("entities", [])
    for e in entities_raw:
        e["_rel_path"] = relative_path(e.get("filePath", ""), project_root)
        e["_module"]   = get_module(e.get("filePath", ""), project_root, int(module_index))

    all_modules = sorted({e["_module"] for e in entities_raw if e["_module"] != "unknown"})

    # ── filters ────────────────────────────────────────────────────────────────
    st.subheader("🔍 Filters")

    if all_modules:
        module_filter = st.multiselect("Modules", options=all_modules, default=all_modules)
    else:
        module_filter = []

    status_filter = st.multiselect(
        "Status",
        options=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
        default=["CRITICAL", "WARNING", "NOT_FOUND", "OK"],
    )

    # Collect all unique Java types from data
    all_java_types = sorted({
        col["javaType"]
        for e in entities_raw
        for col in e.get("columns", [])
        if col.get("javaType")
    })
    java_type_filter = st.multiselect(
        "Java field types",
        options=all_java_types,
        default=[],
        placeholder="All types",
        help="Filter entities that contain at least one field of the selected type(s).",
    )

    st.markdown("**LOB field filter**")
    filter_blob = st.checkbox("Show only entities with BLOB fields")
    filter_clob = st.checkbox("Show only entities with CLOB fields")

    search = st.text_input("Search entity / field / column", "").strip().lower()
    show_ok_cols = st.checkbox("Show OK columns", value=True)

# ── apply module filter ────────────────────────────────────────────────────────
if module_filter:
    entities = [e for e in entities_raw if e["_module"] in module_filter]
else:
    entities = entities_raw

# Java type filter: keep entities that have ≥1 column matching selected types
if java_type_filter:
    entities = [
        e for e in entities
        if any(col.get("javaType") in java_type_filter for col in e.get("columns", []))
    ]

# LOB filters
if filter_blob:
    entities = [e for e in entities if any(is_blob_col(c) for c in e.get("columns", []))]
if filter_clob:
    entities = [e for e in entities if any(is_clob_col(c) for c in e.get("columns", []))]

# ── summary metrics ────────────────────────────────────────────────────────────
s = report["summary"]
m = st.columns(6)
m[0].metric("Entities",      s["totalEntities"])
m[1].metric("Columns",       s["totalColumns"])
m[2].metric("🔴 Critical",   s["criticalIssues"])
m[3].metric("🟡 Warnings",   s["warnings"])
m[4].metric("⚫ Not Found",  s["notFound"])
m[5].metric("🟢 OK",         s["ok"])

# ── type distribution stats ────────────────────────────────────────────────────
with st.expander("📈 Type Distribution", expanded=False):
    all_cols = [col for e in entities_raw for col in e.get("columns", [])]

    tc1, tc2, tc3 = st.columns(3)

    with tc1:
        st.markdown("**Java field types**")
        java_counts = (
            pd.Series([c["javaType"] for c in all_cols if c.get("javaType")])
            .value_counts()
            .rename_axis("type")
            .reset_index(name="count")
        )
        if not java_counts.empty:
            st.dataframe(java_counts, use_container_width=True, hide_index=True, height=280)

    with tc2:
        st.markdown("**Oracle column types**")
        oracle_types = [
            c["oracleColumn"]["dataType"]
            for c in all_cols
            if c.get("oracleColumn") and c["oracleColumn"].get("dataType")
        ]
        if oracle_types:
            oc = (
                pd.Series(oracle_types)
                .value_counts()
                .rename_axis("type")
                .reset_index(name="count")
            )
            st.dataframe(oc, use_container_width=True, hide_index=True, height=280)
        else:
            st.caption("No Oracle data")

    with tc3:
        st.markdown("**Postgres column types**")
        pg_types = [
            c["postgresColumn"]["dataType"]
            for c in all_cols
            if c.get("postgresColumn") and c["postgresColumn"].get("dataType")
        ]
        if pg_types:
            pc = (
                pd.Series(pg_types)
                .value_counts()
                .rename_axis("type")
                .reset_index(name="count")
            )
            st.dataframe(pc, use_container_width=True, hide_index=True, height=280)
        else:
            st.caption("No Postgres data")

st.divider()

# ── flatten all columns into a dataframe ──────────────────────────────────────
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
            "Module":        entity["_module"],
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
            "_entity_status": entity["entityStatus"],
            "_issues":       "\n".join(col.get("issues") or []),
        })

df_all = pd.DataFrame(rows) if rows else pd.DataFrame()

def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
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

df_filtered = apply_filters(df_all.copy())

# ── tabs ───────────────────────────────────────────────────────────────────────
tab_overview, tab_entities, tab_issues = st.tabs(
    ["📊 Overview", "📋 By Entity", "⚠️ Issues Only"]
)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — Overview table
# ──────────────────────────────────────────────────────────────────────────────
with tab_overview:
    display_cols = [
        "Module", "Entity", "Table",
        "Java Field", "Java Column", "Java Type",
        "Oracle Type", "Postgres Type",
        "Oracle ✓", "Postgres ✓", "Status",
    ]
    if not df_filtered.empty:
        visible = df_filtered[[c for c in display_cols if c in df_filtered.columns]]
        styled = visible.style.map(color_cell, subset=["Oracle ✓", "Postgres ✓", "Status"])
        st.dataframe(styled, use_container_width=True, height=520)
        st.caption(f"Showing {len(df_filtered)} column(s) across {df_filtered['Entity'].nunique()} entity/entities")
    else:
        st.info("No columns match the current filters.")

# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — Per-entity detail
# ──────────────────────────────────────────────────────────────────────────────
with tab_entities:
    sorted_entities = sorted(entities, key=lambda e: -severity(e["entityStatus"]))

    for entity in sorted_entities:
        estat = entity["entityStatus"]
        emoji = STATUS_EMOJI.get(estat, "")
        short_class = entity["entityClass"].split(".")[-1]
        module_tag  = f"`{entity['_module']}`  " if all_modules else ""
        label = f"{emoji} {module_tag}**{short_class}**  —  `{entity['tableName']}`"

        # Filter columns for display
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
        if java_type_filter:
            has_type = any(
                c.get("javaType") in java_type_filter
                for c in entity.get("columns", [])
            )
            if not has_type:
                continue
        if not entity_cols and search:
            continue

        with st.expander(label, expanded=(estat in ("CRITICAL", "WARNING"))):

            # ── header row: file path + open button ───────────────────────────
            h1, h2 = st.columns([5, 1])
            with h1:
                rel = entity["_rel_path"]
                st.markdown(
                    f"📄 `{rel}`",
                    help=entity.get("filePath") or "No file path available",
                )
            with h2:
                file_path = entity.get("filePath")
                if file_path and st.button(
                    "💡 Open in IDEA",
                    key=f"idea_{entity['entityClass']}",
                    help=file_path,
                ):
                    open_intellij(file_path, idea_exe)

            # ── DB found status ────────────────────────────────────────────────
            db1, db2 = st.columns(2)
            with db1:
                icon = "✅" if entity["oracleTableFound"] else "❌"
                st.markdown(f"Oracle table: {icon} {'found' if entity['oracleTableFound'] else '**NOT FOUND**'}")
            with db2:
                icon = "✅" if entity["postgresTableFound"] else "❌"
                st.markdown(f"Postgres table: {icon} {'found' if entity['postgresTableFound'] else '**NOT FOUND**'}")

            # ── column table ───────────────────────────────────────────────────
            col_rows = []
            for col in entity_cols:
                oc = col.get("oracleColumn")  or {}
                pc = col.get("postgresColumn") or {}
                flags = []
                if col.get("isId"):         flags.append("PK")
                if col.get("isLob"):        flags.append("LOB")
                if col.get("isJoinColumn"): flags.append("FK")
                col_rows.append({
                    "Field":       col["javaFieldName"],
                    "Column":      col["javaColumnName"],
                    "Java Type":   col["javaType"] + (" [" + ",".join(flags) + "]" if flags else ""),
                    "Oracle":      oc.get("rawDataType", "—"),
                    "Postgres":    pc.get("rawDataType", "—"),
                    "Oracle ✓":    col["oracleCompatibility"],
                    "Postgres ✓":  col["postgresCompatibility"],
                    "Status":      col["overallStatus"],
                })

            if col_rows:
                cdf = pd.DataFrame(col_rows)
                st.dataframe(
                    cdf.style.map(color_cell, subset=["Oracle ✓", "Postgres ✓", "Status"]),
                    use_container_width=True,
                    hide_index=True,
                )

            # ── issues ─────────────────────────────────────────────────────────
            issues = [i for col in entity_cols for i in (col.get("issues") or [])]
            if issues:
                st.markdown("**Issues:**")
                for issue in issues:
                    lvl = "🔴" if "coerces" in issue or "reject" in issue or "CRITICAL" in issue else "🟡"
                    st.markdown(f"{lvl} {issue}")

            # ── unmapped DB columns ────────────────────────────────────────────
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
# TAB 3 — Issues only
# ──────────────────────────────────────────────────────────────────────────────
with tab_issues:
    issue_rows = []
    for entity in entities:
        for col in entity.get("columns", []):
            for issue in (col.get("issues") or []):
                issue_rows.append({
                    "Status":    col["overallStatus"],
                    "Module":    entity["_module"],
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
        st.dataframe(
            idf.style.map(color_cell, subset=["Status"]),
            use_container_width=True,
            height=520,
            hide_index=True,
        )
        st.caption(f"{len(idf)} issue(s)")
    else:
        st.success("No issues match the current filters.")
