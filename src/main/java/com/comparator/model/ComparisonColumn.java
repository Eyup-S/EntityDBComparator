package com.comparator.model;

import java.util.List;

public class ComparisonColumn {
    public String javaFieldName;
    public String javaColumnName;
    public String javaType;
    public boolean isLob;
    public boolean isId;
    public boolean isJoinColumn;

    public DbColumn oracleColumn;
    public DbColumn postgresColumn;

    /** OK | WARNING | CRITICAL | NOT_FOUND */
    public String oracleCompatibility;
    /** OK | WARNING | CRITICAL | NOT_FOUND */
    public String postgresCompatibility;
    /** Worst of the two: CRITICAL > WARNING > NOT_FOUND > OK */
    public String overallStatus;

    public List<String> issues;
}
