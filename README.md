# EntityDBComparator

Detects type mismatches between Spring JPA entities and Oracle / PostgreSQL schemas. Useful during Oracle → Postgres migrations.

---

## Requirements

- Java 11+
- Maven 3.6+
- Python 3.9+ with Streamlit (`pip install streamlit pandas`)

---

## Build

```bash
mvn package
```

This produces `target/entity-db-comparator-1.0.0-fat.jar`.

---

## Usage

Run the four steps in order. Each step writes a JSON file that the next step reads.

### 1. Parse entities

Walks your Spring source tree and extracts all `@Entity` classes with their mapped columns.

```bash
java -jar target/entity-db-comparator-1.0.0-fat.jar entities \
  --source <YOUR_PROJECT>/src/main/java \
  --output entities.json
```

### 2. Extract Oracle schema

Connects to Oracle and dumps table/column metadata.

```bash
java -jar target/entity-db-comparator-1.0.0-fat.jar oracle \
  --url    jdbc:oracle:thin:@//<HOST>:<PORT>/<SERVICE_NAME> \
  --user   <USERNAME> \
  --pass   <PASSWORD> \
  --schema <SCHEMA_NAME> \
  --output oracle.json
```

### 3. Extract Postgres schema

```bash
java -jar target/entity-db-comparator-1.0.0-fat.jar postgres \
  --url    jdbc:postgresql://<HOST>:<PORT>/<DB_NAME> \
  --user   <USERNAME> \
  --pass   <PASSWORD> \
  --schema <SCHEMA_NAME> \
  --output postgres.json
```

### 4. Compare

Merges the three JSON files and produces a report.

```bash
java -jar target/entity-db-comparator-1.0.0-fat.jar compare \
  --entities entities.json \
  --oracle   oracle.json \
  --postgres postgres.json \
  --output   report.json
```

You can omit `--oracle` or `--postgres` if you only have one DB available — missing columns will be marked `NOT_FOUND`.

---

## Viewer

Launch the Streamlit dashboard to explore `report.json` visually.

```bash
streamlit run viewer.py report.json
```

Or open the app first and drag-drop the file:

```bash
streamlit run viewer.py
```

Open `http://localhost:8501` in your browser.

### Sidebar controls

| Control | Description |
|---|---|
| **Project root path** | Strips your project prefix from file paths and enables relative path display |
| **Module segment index** | Which path segment to use as the module name (0 = first folder under project root) |
| **Module filter** | Show only entities belonging to selected modules |
| **Status filter** | Show only columns with selected statuses (CRITICAL / WARNING / NOT\_FOUND / OK) |
| **Java field types** | Show only entities that contain at least one field of the selected Java type |
| **BLOB / CLOB** | Show only entities that have `@Lob` fields |
| **Search** | Filter by entity name, field name, or column name |

### Statuses

| Status | Meaning |
|---|---|
| 🔴 CRITICAL | Types are incompatible — will likely fail on Postgres |
| 🟡 WARNING | Types may work but need manual verification (e.g. `Boolean` → `CHAR(1)`) |
| ⚫ NOT\_FOUND | Column or table not found in that database |
| 🟢 OK | Types are compatible |

---

## Open in IntelliJ IDEA (Ubuntu / Snap)

The **💡 Open in IDEA** button in the viewer uses the `idea://` URL scheme. Run these commands **once** per machine to register the handler:

```bash
mkdir -p ~/.local/bin ~/.local/share/applications

cat > ~/.local/bin/idea-url-handler.sh << 'EOF'
#!/bin/bash
URL="$1"
FILE=$(python3 -c "import sys,urllib.parse; u='$URL'; print(urllib.parse.unquote(u.split('file=')[1].split('&')[0]))")
LINE=$(python3 -c "u='$URL'; print(u.split('line=')[1] if 'line=' in u else '1')")
intellij-idea-ultimate --line "$LINE" "$FILE" &
EOF
chmod +x ~/.local/bin/idea-url-handler.sh

cat > ~/.local/share/applications/idea-url-handler.desktop << 'EOF'
[Desktop Entry]
Name=IntelliJ IDEA URL Handler
Exec=/home/$USER/.local/bin/idea-url-handler.sh %u
Terminal=false
Type=Application
MimeType=x-scheme-handler/idea;
EOF

xdg-mime default idea-url-handler.desktop x-scheme-handler/idea
update-desktop-database ~/.local/share/applications/
```

After registering, click **Allow** the first time Chrome or Firefox asks for permission.
