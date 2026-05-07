package com.comparator.compare;

import com.comparator.model.*;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.stream.Collectors;

public class SchemaComparator {

    private final TypeCompatibilityChecker checker = new TypeCompatibilityChecker();

    public ComparisonReport compare(EntitySchema entitySchema,
                                   DbSchema oracleSchema,
                                   DbSchema postgresSchema) {
        ComparisonReport report = new ComparisonReport();
        report.generatedAt = LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        report.entities = new ArrayList<>();

        // Build lookup maps: uppercase table name → DbTable
        Map<String, DbTable> oracleTables = buildTableMap(oracleSchema);
        Map<String, DbTable> postgresTables = buildTableMap(postgresSchema);

        int totalColumns = 0, critical = 0, warnings = 0, notFound = 0, ok = 0;

        for (EntityInfo entity : entitySchema.entities) {
            ComparisonEntity ce = compareEntity(entity, oracleTables, postgresTables);
            report.entities.add(ce);

            for (ComparisonColumn cc : ce.columns) {
                totalColumns++;
                switch (cc.overallStatus) {
                    case "CRITICAL": critical++; break;
                    case "WARNING":  warnings++; break;
                    case "NOT_FOUND": notFound++; break;
                    default: ok++; break;
                }
            }
        }

        ComparisonReport.Summary summary = new ComparisonReport.Summary();
        summary.totalEntities = entitySchema.entities.size();
        summary.totalColumns = totalColumns;
        summary.criticalIssues = critical;
        summary.warnings = warnings;
        summary.notFound = notFound;
        summary.ok = ok;
        report.summary = summary;

        return report;
    }

    // -------------------------------------------------------------------------

    private ComparisonEntity compareEntity(EntityInfo entity,
                                           Map<String, DbTable> oracleTables,
                                           Map<String, DbTable> postgresTables) {
        ComparisonEntity ce = new ComparisonEntity();
        ce.entityClass = entity.fullClassName;
        ce.tableName = entity.tableName;
        ce.columns = new ArrayList<>();

        // Look up table in both DBs (case-insensitive)
        DbTable oracleTable = findTable(entity.tableName, oracleTables);
        DbTable postgresTable = findTable(entity.tableName, postgresTables);

        ce.oracleTableFound = oracleTable != null;
        ce.postgresTableFound = postgresTable != null;

        // Build fast column lookup (uppercase)
        Map<String, DbColumn> oracleCols = buildColumnMap(oracleTable);
        Map<String, DbColumn> postgresCols = buildColumnMap(postgresTable);

        // Track which DB columns were matched
        Set<String> matchedOracle = new HashSet<>();
        Set<String> matchedPostgres = new HashSet<>();

        String worstEntity = "OK";

        for (EntityColumn ec : entity.columns) {
            ComparisonColumn cc = compareColumn(ec, oracleCols, postgresCols);
            ce.columns.add(cc);

            if (cc.oracleColumn != null) matchedOracle.add(cc.oracleColumn.columnName.toUpperCase(java.util.Locale.ROOT));
            if (cc.postgresColumn != null) matchedPostgres.add(cc.postgresColumn.columnName.toUpperCase(java.util.Locale.ROOT));

            worstEntity = worst(worstEntity, cc.overallStatus);
        }

        // Collect unmapped DB columns
        ce.unmappedOracleColumns = oracleCols.keySet().stream()
                .filter(c -> !matchedOracle.contains(c))
                .sorted()
                .collect(Collectors.toList());

        ce.unmappedPostgresColumns = postgresCols.keySet().stream()
                .filter(c -> !matchedPostgres.contains(c.toUpperCase(java.util.Locale.ROOT)))
                .sorted()
                .collect(Collectors.toList());

        if (!ce.oracleTableFound)   worstEntity = worst(worstEntity, "NOT_FOUND");
        if (!ce.postgresTableFound) worstEntity = worst(worstEntity, "NOT_FOUND");

        ce.entityStatus = worstEntity;
        return ce;
    }

    private ComparisonColumn compareColumn(EntityColumn ec,
                                           Map<String, DbColumn> oracleCols,
                                           Map<String, DbColumn> postgresCols) {
        ComparisonColumn cc = new ComparisonColumn();
        cc.javaFieldName = ec.fieldName;
        cc.javaColumnName = ec.columnName;
        cc.javaType = ec.rawJavaType != null ? ec.rawJavaType : ec.javaType;
        cc.isLob = ec.isLob;
        cc.isId = ec.isId;
        cc.isJoinColumn = ec.isJoinColumn;
        cc.issues = new ArrayList<>();

        String key = ec.columnName.toUpperCase(java.util.Locale.ROOT);
        cc.oracleColumn = oracleCols.get(key);
        cc.postgresColumn = postgresCols.get(key);

        // Oracle compatibility
        if (cc.oracleColumn == null) {
            cc.oracleCompatibility = "NOT_FOUND";
            cc.issues.add("Column '" + ec.columnName + "' not found in Oracle schema.");
        } else {
            TypeCompatibilityChecker.CheckResult r = checker.check(ec, cc.oracleColumn, "oracle");
            cc.oracleCompatibility = r.status;
            if (r.message != null) cc.issues.add("[Oracle] " + r.message);
        }

        // Postgres compatibility
        if (cc.postgresColumn == null) {
            cc.postgresCompatibility = "NOT_FOUND";
            cc.issues.add("Column '" + ec.columnName + "' not found in Postgres schema.");
        } else {
            TypeCompatibilityChecker.CheckResult r = checker.check(ec, cc.postgresColumn, "postgres");
            cc.postgresCompatibility = r.status;
            if (r.message != null) cc.issues.add("[Postgres] " + r.message);
        }

        cc.overallStatus = worst(cc.oracleCompatibility, cc.postgresCompatibility);
        return cc;
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private Map<String, DbTable> buildTableMap(DbSchema schema) {
        Map<String, DbTable> map = new HashMap<>();
        if (schema == null || schema.tables == null) return map;
        for (DbTable t : schema.tables) {
            map.put(t.tableName.toUpperCase(java.util.Locale.ROOT), t);
        }
        return map;
    }

    private Map<String, DbColumn> buildColumnMap(DbTable table) {
        Map<String, DbColumn> map = new LinkedHashMap<>();
        if (table == null || table.columns == null) return map;
        for (DbColumn c : table.columns) {
            map.put(c.columnName.toUpperCase(java.util.Locale.ROOT), c);
        }
        return map;
    }

    private DbTable findTable(String name, Map<String, DbTable> map) {
        if (name == null) return null;
        // Try exact uppercase match first
        DbTable t = map.get(name.toUpperCase(java.util.Locale.ROOT));
        if (t != null) return t;
        // Try lowercase (Postgres default)
        return map.get(name.toLowerCase());
    }

    /** Returns the more severe of two statuses: CRITICAL > WARNING > NOT_FOUND > OK */
    private String worst(String a, String b) {
        return severity(a) >= severity(b) ? a : b;
    }

    private int severity(String status) {
        switch (status == null ? "OK" : status) {
            case "CRITICAL":  return 3;
            case "WARNING":   return 2;
            case "NOT_FOUND": return 1;
            default:          return 0;
        }
    }
}
