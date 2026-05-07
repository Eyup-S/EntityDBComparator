package com.comparator.model;

public class EntityColumn {
    public String fieldName;
    /** Column name resolved from @Column(name=...), @JoinColumn(name=...), or field name fallback */
    public String columnName;
    /** Simple Java type, e.g. "String", "Long", "LocalDateTime" */
    public String javaType;
    /** Full type as written in source, including generics */
    public String rawJavaType;
    public boolean isLob;
    public boolean isId;
    public boolean isJoinColumn;
    public boolean isEnumerated;
    /** STRING or ORDINAL from @Enumerated */
    public String enumeratedType;
    /** Value from @Column(columnDefinition=...) if present */
    public String columnDefinition;
    public boolean nullable = true;
}
