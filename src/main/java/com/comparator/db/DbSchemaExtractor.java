package com.comparator.db;

import com.comparator.model.DbColumn;
import com.comparator.model.DbSchema;
import com.comparator.model.DbTable;

import java.sql.*;
import java.util.*;
import java.util.Locale;

public class DbSchemaExtractor {

    // -------------------------------------------------------------------------
    // Oracle
    // -------------------------------------------------------------------------

    private static final String ORACLE_QUERY = ""
            + "SELECT c.table_name, c.column_name, c.data_type, "
            + "       c.char_length          AS character_max_length, "
            + "       c.data_precision       AS numeric_precision, "
            + "       c.data_scale           AS numeric_scale, "
            + "       c.nullable, "
            + "       c.data_default         AS column_default, "
            + "       c.column_id            AS ordinal_position "
            + "FROM   all_tab_columns c "
            + "INNER  JOIN all_tables t "
            + "       ON t.table_name = c.table_name AND t.owner = c.owner "
            + "WHERE  c.owner = UPPER(?) "
            + "ORDER  BY c.table_name, c.column_id";

    // -------------------------------------------------------------------------
    // PostgreSQL
    // -------------------------------------------------------------------------

    private static final String POSTGRES_QUERY = ""
            + "SELECT c.table_name, c.column_name, c.data_type, "
            + "       c.character_maximum_length, "
            + "       c.numeric_precision, "
            + "       c.numeric_scale, "
            + "       c.is_nullable, "
            + "       c.column_default, "
            + "       c.udt_name, "
            + "       c.ordinal_position "
            + "FROM   information_schema.columns c "
            + "INNER  JOIN information_schema.tables t "
            + "       ON t.table_name = c.table_name AND t.table_schema = c.table_schema "
            + "WHERE  c.table_schema = ? "
            + "  AND  t.table_type = 'BASE TABLE' "
            + "ORDER  BY c.table_name, c.ordinal_position";

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    public DbSchema extractOracle(String jdbcUrl, String user, String password, String schema) throws SQLException {
        DbSchema result = new DbSchema();
        result.dbType = "oracle";
        result.schemaName = schema.toUpperCase(Locale.ROOT);
        result.tables = new ArrayList<>();

        log("Connecting to Oracle...");
        long t0 = System.currentTimeMillis();
        try (Connection conn = DriverManager.getConnection(jdbcUrl, user, password)) {
            log("Connected in %d ms. Running schema query for owner [%s]...", elapsed(t0), schema.toUpperCase(Locale.ROOT));
            long t1 = System.currentTimeMillis();
            try (PreparedStatement ps = conn.prepareStatement(ORACLE_QUERY)) {
                ps.setString(1, schema);
                log("Query sent, waiting for results...");
                try (ResultSet rs = ps.executeQuery()) {
                    log("First rows received in %d ms. Reading columns...", elapsed(t1));
                    result.tables = mapOracleRows(rs, schema.toUpperCase(Locale.ROOT));
                }
            }
        }
        log("Done. %d tables, %d columns total in %d ms.",
                result.tables.size(),
                result.tables.stream().mapToInt(t -> t.columns.size()).sum(),
                elapsed(t0));
        return result;
    }

    public DbSchema extractPostgres(String jdbcUrl, String user, String password, String schema) throws SQLException {
        DbSchema result = new DbSchema();
        result.dbType = "postgres";
        result.schemaName = schema;
        result.tables = new ArrayList<>();

        log("Connecting to Postgres...");
        long t0 = System.currentTimeMillis();
        try (Connection conn = DriverManager.getConnection(jdbcUrl, user, password)) {
            log("Connected in %d ms. Running schema query for schema [%s]...", elapsed(t0), schema);
            long t1 = System.currentTimeMillis();
            try (PreparedStatement ps = conn.prepareStatement(POSTGRES_QUERY)) {
                ps.setString(1, schema);
                log("Query sent, waiting for results...");
                try (ResultSet rs = ps.executeQuery()) {
                    log("First rows received in %d ms. Reading columns...", elapsed(t1));
                    result.tables = mapPostgresRows(rs, schema);
                }
            }
        }
        log("Done. %d tables, %d columns total in %d ms.",
                result.tables.size(),
                result.tables.stream().mapToInt(t -> t.columns.size()).sum(),
                elapsed(t0));
        return result;
    }

    // -------------------------------------------------------------------------
    // Row mapping
    // -------------------------------------------------------------------------

    private List<DbTable> mapOracleRows(ResultSet rs, String schema) throws SQLException {
        Map<String, DbTable> tableMap = new LinkedHashMap<>();
        int rowCount = 0;

        while (rs.next()) {
            rowCount++;
            String tableName = rs.getString("table_name").toUpperCase(Locale.ROOT);
            boolean isNew = !tableMap.containsKey(tableName);
            DbTable table = tableMap.computeIfAbsent(tableName, k -> {
                DbTable t = new DbTable();
                t.tableName = k;
                t.schemaName = schema;
                t.columns = new ArrayList<>();
                return t;
            });
            if (isNew) {
                log("  Reading table %-40s (table #%d)", tableName, tableMap.size());
            }

            DbColumn col = new DbColumn();
            col.columnName = rs.getString("column_name").toUpperCase(Locale.ROOT);
            col.dataType = rs.getString("data_type").toUpperCase(Locale.ROOT);
            col.characterMaxLength = getIntOrNull(rs, "character_max_length");
            col.numericPrecision = getIntOrNull(rs, "numeric_precision");
            col.numericScale = getIntOrNull(rs, "numeric_scale");
            col.nullable = "Y".equalsIgnoreCase(rs.getString("nullable"));
            col.defaultValue = rs.getString("column_default");
            col.rawDataType = buildOracleRawType(col);

            table.columns.add(col);
        }

        return new ArrayList<>(tableMap.values());
    }

    private List<DbTable> mapPostgresRows(ResultSet rs, String schema) throws SQLException {
        Map<String, DbTable> tableMap = new LinkedHashMap<>();
        int rowCount = 0;

        while (rs.next()) {
            rowCount++;
            String tableName = rs.getString("table_name");
            boolean isNew = !tableMap.containsKey(tableName);
            DbTable table = tableMap.computeIfAbsent(tableName, k -> {
                DbTable t = new DbTable();
                t.tableName = k;
                t.schemaName = schema;
                t.columns = new ArrayList<>();
                return t;
            });
            if (isNew) {
                log("  Reading table %-40s (table #%d)", tableName, tableMap.size());
            }

            DbColumn col = new DbColumn();
            col.columnName = rs.getString("column_name");
            col.dataType = rs.getString("data_type");
            col.characterMaxLength = getIntOrNull(rs, "character_maximum_length");
            col.numericPrecision = getIntOrNull(rs, "numeric_precision");
            col.numericScale = getIntOrNull(rs, "numeric_scale");
            col.nullable = "YES".equalsIgnoreCase(rs.getString("is_nullable"));
            col.defaultValue = rs.getString("column_default");
            col.udtName = rs.getString("udt_name");
            col.rawDataType = col.dataType;

            table.columns.add(col);
        }

        return new ArrayList<>(tableMap.values());
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private Integer getIntOrNull(ResultSet rs, String col) throws SQLException {
        int val = rs.getInt(col);
        return rs.wasNull() ? null : val;
    }

    private static void log(String fmt, Object... args) {
        System.out.printf("[%s] " + fmt + "%n",
                java.time.LocalTime.now().withNano(0), args);
        System.out.flush();
    }

    private static long elapsed(long startMs) {
        return System.currentTimeMillis() - startMs;
    }

    private String buildOracleRawType(DbColumn col) {
        String base = col.dataType;
        if (col.numericPrecision != null && col.numericScale != null) {
            return base + "(" + col.numericPrecision + "," + col.numericScale + ")";
        } else if (col.numericPrecision != null) {
            return base + "(" + col.numericPrecision + ")";
        } else if (col.characterMaxLength != null && col.characterMaxLength > 0) {
            return base + "(" + col.characterMaxLength + ")";
        }
        return base;
    }
}
