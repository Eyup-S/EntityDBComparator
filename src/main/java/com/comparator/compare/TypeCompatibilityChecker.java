package com.comparator.compare;

import com.comparator.model.DbColumn;
import com.comparator.model.EntityColumn;

import java.util.*;
import java.util.Locale;

/**
 * Maps Java types and DB types to abstract categories, then checks compatibility.
 *
 * The key scenario this catches: a Java String field backed by a NUMBER column —
 * Oracle silently coerces but Postgres throws a type error.
 */
public class TypeCompatibilityChecker {

    public enum JavaCategory {
        STRING, CLOB, INTEGER, LONG, DECIMAL, FLOAT, BOOLEAN,
        DATE, DATETIME, TIMESTAMP, TIMESTAMP_TZ,
        BLOB, BINARY, UUID, ENUM_STRING, ENUM_ORDINAL, UNKNOWN
    }

    public enum DbCategory {
        STRING, CLOB, INTEGER, LONG, NUMERIC, FLOAT, BOOLEAN,
        DATE, TIMESTAMP, TIMESTAMP_TZ,
        BLOB, BINARY, JSON, UUID, UNKNOWN
    }

    public static class CheckResult {
        public final String status;   // OK | WARNING | CRITICAL
        public final String message;

        CheckResult(String status, String message) {
            this.status = status;
            this.message = message;
        }
    }

    // -------------------------------------------------------------------------
    // Public entry point
    // -------------------------------------------------------------------------

    public CheckResult check(EntityColumn entityCol, DbColumn dbCol, String dbType) {
        JavaCategory jcat = toJavaCategory(entityCol);
        DbCategory dcat = toDbCategory(dbCol, dbType);

        return evaluate(jcat, dcat, entityCol, dbCol, dbType);
    }

    // -------------------------------------------------------------------------
    // Java type → category
    // -------------------------------------------------------------------------

    public JavaCategory toJavaCategory(EntityColumn col) {
        String type = col.javaType;
        boolean lob = col.isLob;

        if (col.isEnumerated) {
            return "STRING".equals(col.enumeratedType) ? JavaCategory.ENUM_STRING : JavaCategory.ENUM_ORDINAL;
        }

        // Normalize: strip trailing [] to check base type
        String base = type.replace("[]", "").trim();

        if (base.equals("byte") || base.equals("Byte")) {
            return lob ? JavaCategory.BLOB : JavaCategory.BINARY;
        }

        switch (base) {
            case "String":
            case "StringBuilder":
            case "StringBuffer":
            case "CharSequence":
                return lob ? JavaCategory.CLOB : JavaCategory.STRING;

            case "char":
            case "Character":
                return JavaCategory.STRING;

            case "int":
            case "Integer":
            case "short":
            case "Short":
            case "AtomicInteger":
                return JavaCategory.INTEGER;

            case "long":
            case "Long":
            case "AtomicLong":
                return JavaCategory.LONG;

            case "BigDecimal":
            case "BigInteger":
                return JavaCategory.DECIMAL;

            case "double":
            case "Double":
            case "float":
            case "Float":
                return JavaCategory.FLOAT;

            case "boolean":
            case "Boolean":
                return JavaCategory.BOOLEAN;

            case "Date":
                // java.util.Date / java.sql.Date — treat as DATETIME since
                // Oracle DATE includes time and java.util.Date also does
                return JavaCategory.DATETIME;

            case "LocalDate":
            case "YearMonth":
                return JavaCategory.DATE;

            case "LocalDateTime":
            case "Timestamp":
            case "Calendar":
                return JavaCategory.TIMESTAMP;

            case "ZonedDateTime":
            case "OffsetDateTime":
            case "Instant":
                return JavaCategory.TIMESTAMP_TZ;

            case "UUID":
                return JavaCategory.UUID;

            default:
                return JavaCategory.UNKNOWN;
        }
    }

    // -------------------------------------------------------------------------
    // DB type → category
    // -------------------------------------------------------------------------

    public DbCategory toDbCategory(DbColumn col, String dbType) {
        String t = col.dataType.toUpperCase(Locale.ROOT).trim();

        if ("oracle".equals(dbType)) {
            return oracleCategory(t, col);
        } else {
            return postgresCategory(t, col);
        }
    }

    private DbCategory oracleCategory(String t, DbColumn col) {
        switch (t) {
            case "VARCHAR2":
            case "VARCHAR":
            case "CHAR":
            case "NVARCHAR2":
            case "NCHAR":
                return DbCategory.STRING;

            case "CLOB":
            case "NCLOB":
            case "LONG":
                return DbCategory.CLOB;

            case "NUMBER":
            case "NUMERIC":
            case "DECIMAL":
                // NUMBER with scale 0 or no scale → integer-ish; scale > 0 → decimal
                if (col.numericScale != null && col.numericScale > 0) return DbCategory.NUMERIC;
                if (col.numericPrecision != null) {
                    if (col.numericPrecision <= 9) return DbCategory.INTEGER;
                    if (col.numericPrecision <= 18) return DbCategory.LONG;
                }
                return DbCategory.NUMERIC; // unconstrained NUMBER
            case "INTEGER":
            case "INT":
            case "SMALLINT":
            case "PLS_INTEGER":
            case "BINARY_INTEGER":
                return DbCategory.INTEGER;

            case "FLOAT":
            case "BINARY_FLOAT":
            case "BINARY_DOUBLE":
            case "REAL":
                return DbCategory.FLOAT;

            case "DATE":
                return DbCategory.TIMESTAMP; // Oracle DATE has time component

            case "TIMESTAMP":
            case "TIMESTAMP(3)":
            case "TIMESTAMP(6)":
            case "TIMESTAMP(9)":
                return DbCategory.TIMESTAMP;

            case "TIMESTAMP WITH TIME ZONE":
            case "TIMESTAMP WITH LOCAL TIME ZONE":
                return DbCategory.TIMESTAMP_TZ;

            case "BLOB":
            case "LONG RAW":
                return DbCategory.BLOB;

            case "RAW":
                return DbCategory.BINARY;

            case "BOOLEAN":
                return DbCategory.BOOLEAN;

            case "XMLTYPE":
            case "SDO_GEOMETRY":
                return DbCategory.UNKNOWN;

            default:
                if (t.startsWith("TIMESTAMP")) return DbCategory.TIMESTAMP;
                if (t.startsWith("INTERVAL")) return DbCategory.UNKNOWN;
                return DbCategory.UNKNOWN;
        }
    }

    private DbCategory postgresCategory(String t, DbColumn col) {
        // Postgres data_type values from information_schema are verbose
        switch (t) {
            case "CHARACTER VARYING":
            case "VARCHAR":
            case "CHARACTER":
            case "CHAR":
            case "BPCHAR":
            case "NAME":
                return DbCategory.STRING;

            case "TEXT":
                return DbCategory.CLOB; // text is unbounded — closest to CLOB

            case "INTEGER":
            case "INT":
            case "INT4":
            case "INT2":
            case "SMALLINT":
            case "SERIAL":
            case "SMALLSERIAL":
                return DbCategory.INTEGER;

            case "BIGINT":
            case "INT8":
            case "BIGSERIAL":
                return DbCategory.LONG;

            case "NUMERIC":
            case "DECIMAL":
                if (col.numericScale != null && col.numericScale > 0) return DbCategory.NUMERIC;
                if (col.numericPrecision != null) {
                    if (col.numericPrecision <= 9) return DbCategory.INTEGER;
                    if (col.numericPrecision <= 18) return DbCategory.LONG;
                }
                return DbCategory.NUMERIC;

            case "REAL":
            case "FLOAT4":
            case "DOUBLE PRECISION":
            case "FLOAT8":
            case "FLOAT":
                return DbCategory.FLOAT;

            case "BOOLEAN":
            case "BOOL":
                return DbCategory.BOOLEAN;

            case "DATE":
                return DbCategory.DATE; // Postgres DATE has NO time

            case "TIMESTAMP WITHOUT TIME ZONE":
            case "TIMESTAMP":
                return DbCategory.TIMESTAMP;

            case "TIMESTAMP WITH TIME ZONE":
            case "TIMESTAMPTZ":
                return DbCategory.TIMESTAMP_TZ;

            case "BYTEA":
                return DbCategory.BLOB;

            case "OID":
            case "LO":
                return DbCategory.BLOB;

            case "JSON":
            case "JSONB":
                return DbCategory.JSON;

            case "UUID":
                return DbCategory.UUID;

            case "XML":
                return DbCategory.CLOB;

            case "USER-DEFINED":
                // udtName may tell us more (e.g., "citext")
                if (col.udtName != null) {
                    String udt = col.udtName.toLowerCase();
                    if (udt.equals("citext")) return DbCategory.STRING;
                    if (udt.equals("bytea")) return DbCategory.BLOB;
                    if (udt.equals("uuid")) return DbCategory.UUID;
                }
                return DbCategory.UNKNOWN;

            default:
                if (t.startsWith("TIMESTAMP")) return DbCategory.TIMESTAMP;
                if (t.startsWith("CHARACTER")) return DbCategory.STRING;
                return DbCategory.UNKNOWN;
        }
    }

    // -------------------------------------------------------------------------
    // Compatibility evaluation
    // -------------------------------------------------------------------------

    private CheckResult evaluate(JavaCategory jcat, DbCategory dcat,
                                 EntityColumn entityCol, DbColumn dbCol, String dbType) {
        // Exact and obviously safe mappings
        if (isDirectlyCompatible(jcat, dcat)) {
            return new CheckResult("OK", null);
        }

        // Critical: Java String mapped to a numeric column
        // This is the #1 migration trap: Oracle auto-casts, Postgres rejects it.
        if (jcat == JavaCategory.STRING || jcat == JavaCategory.CLOB) {
            if (dcat == DbCategory.INTEGER || dcat == DbCategory.LONG
                    || dcat == DbCategory.NUMERIC || dcat == DbCategory.FLOAT) {
                return new CheckResult("CRITICAL",
                        "Java " + entityCol.javaType + " mapped to DB type " + dbCol.rawDataType
                                + " — Oracle coerces silently but Postgres will reject non-numeric values.");
            }
        }

        // Critical: numeric Java type mapped to a string column
        if ((jcat == JavaCategory.INTEGER || jcat == JavaCategory.LONG
                || jcat == JavaCategory.DECIMAL || jcat == JavaCategory.FLOAT)
                && (dcat == DbCategory.STRING || dcat == DbCategory.CLOB)) {
            return new CheckResult("CRITICAL",
                    "Java " + entityCol.javaType + " mapped to DB type " + dbCol.rawDataType
                            + " — type mismatch may fail on Postgres.");
        }

        // Boolean mapped to CHAR or numeric in Oracle
        if (jcat == JavaCategory.BOOLEAN) {
            if (dcat == DbCategory.STRING) {
                return new CheckResult("WARNING",
                        "Java Boolean mapped to " + dbType + " type " + dbCol.rawDataType
                                + " — likely 'Y'/'N' or 'true'/'false' mapping. Verify the converter.");
            }
            if (dcat == DbCategory.INTEGER || dcat == DbCategory.NUMERIC) {
                return new CheckResult("WARNING",
                        "Java Boolean mapped to " + dbType + " numeric type " + dbCol.rawDataType
                                + " — 0/1 mapping. Verify this works under Postgres.");
            }
        }

        // Oracle DATE → Java LocalDate: Oracle DATE has time; LocalDate silently drops it
        if (jcat == JavaCategory.DATE && dcat == DbCategory.TIMESTAMP && "oracle".equals(dbType)) {
            return new CheckResult("WARNING",
                    "Java LocalDate mapped to Oracle DATE (which stores time). Time part will be lost on read-back.");
        }

        // Java LocalDateTime → Postgres DATE (no time stored)
        if ((jcat == JavaCategory.DATETIME || jcat == JavaCategory.TIMESTAMP)
                && dcat == DbCategory.DATE && "postgres".equals(dbType)) {
            return new CheckResult("CRITICAL",
                    "Java " + entityCol.javaType + " mapped to Postgres DATE — time component will be dropped.");
        }

        // Enum ordinal → string column (or vice versa)
        if (jcat == JavaCategory.ENUM_ORDINAL && dcat == DbCategory.STRING) {
            return new CheckResult("WARNING",
                    "@Enumerated(ORDINAL) but DB column is a string type — ordinal stored as number, not label.");
        }
        if (jcat == JavaCategory.ENUM_STRING && (dcat == DbCategory.INTEGER || dcat == DbCategory.NUMERIC)) {
            return new CheckResult("CRITICAL",
                    "@Enumerated(STRING) but DB column is numeric — Postgres will reject the enum label.");
        }

        // BLOB → Postgres bytea is fine
        if ((jcat == JavaCategory.BLOB || jcat == JavaCategory.BINARY) && dcat == DbCategory.BLOB) {
            return new CheckResult("OK", null);
        }

        // CLOB → Postgres text is fine
        if (jcat == JavaCategory.CLOB && dcat == DbCategory.CLOB) {
            return new CheckResult("OK", null);
        }

        // UUID
        if (jcat == JavaCategory.UUID && (dcat == DbCategory.UUID || dcat == DbCategory.STRING)) {
            return new CheckResult("OK", null);
        }

        // Unknown DB type — don't claim OK, but don't fail either
        if (dcat == DbCategory.UNKNOWN || jcat == JavaCategory.UNKNOWN) {
            return new CheckResult("WARNING",
                    "Could not determine type category for "
                            + (jcat == JavaCategory.UNKNOWN ? "Java type " + entityCol.javaType : "")
                            + (dcat == DbCategory.UNKNOWN ? " DB type " + dbCol.rawDataType : "")
                            + " — manual check required.");
        }

        // JSON → String is fine in many mappings
        if (dcat == DbCategory.JSON && (jcat == JavaCategory.STRING || jcat == JavaCategory.CLOB)) {
            return new CheckResult("OK", null);
        }

        // Default: flag as warning for anything not explicitly handled
        return new CheckResult("WARNING",
                "Java " + entityCol.javaType + " vs " + dbType + " type " + dbCol.rawDataType
                        + " — compatibility not confirmed, verify manually.");
    }

    private boolean isDirectlyCompatible(JavaCategory jcat, DbCategory dcat) {
        switch (jcat) {
            case STRING:
                return dcat == DbCategory.STRING || dcat == DbCategory.JSON;
            case CLOB:
                return dcat == DbCategory.CLOB || dcat == DbCategory.STRING; // text in PG is fine
            case INTEGER:
                return dcat == DbCategory.INTEGER || dcat == DbCategory.LONG
                        || dcat == DbCategory.NUMERIC;
            case LONG:
                return dcat == DbCategory.LONG || dcat == DbCategory.NUMERIC;
            case DECIMAL:
                return dcat == DbCategory.NUMERIC || dcat == DbCategory.LONG
                        || dcat == DbCategory.INTEGER;
            case FLOAT:
                return dcat == DbCategory.FLOAT || dcat == DbCategory.NUMERIC;
            case BOOLEAN:
                return dcat == DbCategory.BOOLEAN;
            case DATE:
                return dcat == DbCategory.DATE;
            case DATETIME:
                return dcat == DbCategory.TIMESTAMP || dcat == DbCategory.DATE;
            case TIMESTAMP:
                return dcat == DbCategory.TIMESTAMP || dcat == DbCategory.TIMESTAMP_TZ;
            case TIMESTAMP_TZ:
                return dcat == DbCategory.TIMESTAMP_TZ || dcat == DbCategory.TIMESTAMP;
            case BLOB:
                return dcat == DbCategory.BLOB || dcat == DbCategory.BINARY;
            case BINARY:
                return dcat == DbCategory.BINARY || dcat == DbCategory.BLOB;
            case UUID:
                return dcat == DbCategory.UUID;
            case ENUM_STRING:
                return dcat == DbCategory.STRING;
            case ENUM_ORDINAL:
                return dcat == DbCategory.INTEGER || dcat == DbCategory.NUMERIC;
            default:
                return false;
        }
    }
}
