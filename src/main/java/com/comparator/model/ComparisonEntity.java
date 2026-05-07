package com.comparator.model;

import java.util.List;

public class ComparisonEntity {
    public String entityClass;
    public String tableName;
    /** Absolute path to the .java source file, from EntityParser */
    public String filePath;
    public boolean oracleTableFound;
    public boolean postgresTableFound;
    public List<ComparisonColumn> columns;
    /** Column names present in Oracle but not mapped in any entity field */
    public List<String> unmappedOracleColumns;
    /** Column names present in Postgres but not mapped in any entity field */
    public List<String> unmappedPostgresColumns;
    /** Worst status among all columns */
    public String entityStatus;
}
