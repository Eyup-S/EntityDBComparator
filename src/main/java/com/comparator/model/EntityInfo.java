package com.comparator.model;

import java.util.List;

public class EntityInfo {
    public String className;
    public String fullClassName;
    public String filePath;
    /** Table name from @Table(name=...), fallback to class name upper-cased */
    public String tableName;
    /** Schema from @Table(schema=...) or extracted from "schema.table" in name attribute */
    public String schemaName;
    public List<EntityColumn> columns;
}
