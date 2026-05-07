package com.comparator.model;

import java.util.List;

public class DbSchema {
    public String extractedAt;
    /** "oracle" or "postgres" */
    public String dbType;
    public String schemaName;
    public List<DbTable> tables;
}
