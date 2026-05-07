package com.comparator.model;

public class DbColumn {
    public String columnName;
    public String dataType;
    public Integer characterMaxLength;
    public Integer numericPrecision;
    public Integer numericScale;
    public boolean nullable;
    public String defaultValue;
    /** Postgres udt_name for user-defined / special types (e.g. "int4", "bytea") */
    public String udtName;
    /** Full original type string as reported by the DB, e.g. "NUMBER(19,0)" or "character varying" */
    public String rawDataType;
}
