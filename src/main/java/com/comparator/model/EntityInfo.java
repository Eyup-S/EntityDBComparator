package com.comparator.model;

import java.util.List;

public class EntityInfo {
    public String className;
    public String fullClassName;
    public String filePath;
    /** Table name from @Table(name=...), fallback to class name upper-cased */
    public String tableName;
    public List<EntityColumn> columns;
}
