package com.comparator;

import com.comparator.compare.SchemaComparator;
import com.comparator.db.DbSchemaExtractor;
import com.comparator.model.*;
import com.comparator.parser.EntityParser;
import com.comparator.report.JsonReporter;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * CLI entry point.
 *
 * Commands:
 *   entities  --source <path>   [--output entities.json]
 *   oracle    --url <jdbc-url> --user <u> --pass <p> --schema <s>  [--output oracle.json]
 *   postgres  --url <jdbc-url> --user <u> --pass <p> --schema <s>  [--output postgres.json]
 *   compare   --entities <file> [--oracle <file>] [--postgres <file>] [--output report.json]
 */
public class Main {

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            printHelp();
            System.exit(1);
        }

        String command = args[0];
        Map<String, String> params = parseArgs(args, 1);

        JsonReporter reporter = new JsonReporter();

        switch (command) {
            case "entities":
                runEntities(params, reporter);
                break;
            case "oracle":
                runOracle(params, reporter);
                break;
            case "postgres":
                runPostgres(params, reporter);
                break;
            case "compare":
                runCompare(params, reporter);
                break;
            default:
                System.err.println("Unknown command: " + command);
                printHelp();
                System.exit(1);
        }
    }

    // -------------------------------------------------------------------------
    // entities command
    // -------------------------------------------------------------------------

    private static void runEntities(Map<String, String> params, JsonReporter reporter) throws Exception {
        String source = require(params, "source");
        String output = params.getOrDefault("output", "entities.json");

        System.out.println("[INFO] Parsing entities from: " + source);
        EntityParser parser = new EntityParser();
        List<EntityInfo> entities = parser.parseDirectory(source);

        EntitySchema schema = new EntitySchema();
        schema.extractedAt = now();
        schema.sourcePath = source;
        schema.entities = entities;

        System.out.println("[INFO] Found " + entities.size() + " entity class(es).");
        entities.forEach(e -> System.out.printf("       %-40s  table=%s  columns=%d%n",
                e.fullClassName, e.tableName, e.columns.size()));

        reporter.write(schema, output);
    }

    // -------------------------------------------------------------------------
    // oracle command
    // -------------------------------------------------------------------------

    private static void runOracle(Map<String, String> params, JsonReporter reporter) throws Exception {
        String url        = require(params, "url");
        String user       = require(params, "user");
        String pass       = require(params, "pass");
        String schemaArg  = require(params, "schema");
        String output     = params.getOrDefault("output", "oracle.json");

        String[] schemas = schemaArg.split(",");
        DbSchemaExtractor extractor = new DbSchemaExtractor();
        DbSchema merged = null;

        for (String schema : schemas) {
            schema = schema.trim();
            System.out.println("[INFO] Connecting to Oracle: " + url + "  schema=" + schema);
            DbSchema partial = extractor.extractOracle(url, user, pass, schema);
            if (merged == null) {
                merged = partial;
            } else {
                merged.tables.addAll(partial.tables);
            }
            System.out.println("[INFO] Extracted " + partial.tables.size() + " table(s) from Oracle schema [" + schema + "].");
        }

        merged.schemaName = schemaArg;
        merged.extractedAt = now();
        System.out.println("[INFO] Total tables across all schemas: " + merged.tables.size());

        reporter.write(merged, output);
    }

    // -------------------------------------------------------------------------
    // postgres command
    // -------------------------------------------------------------------------

    private static void runPostgres(Map<String, String> params, JsonReporter reporter) throws Exception {
        String url       = require(params, "url");
        String user      = require(params, "user");
        String pass      = require(params, "pass");
        String schemaArg = params.getOrDefault("schema", "public");
        String output    = params.getOrDefault("output", "postgres.json");

        String[] schemas = schemaArg.split(",");
        DbSchemaExtractor extractor = new DbSchemaExtractor();
        DbSchema merged = null;

        for (String schema : schemas) {
            schema = schema.trim();
            System.out.println("[INFO] Connecting to PostgreSQL: " + url + "  schema=" + schema);
            DbSchema partial = extractor.extractPostgres(url, user, pass, schema);
            if (merged == null) {
                merged = partial;
            } else {
                merged.tables.addAll(partial.tables);
            }
            System.out.println("[INFO] Extracted " + partial.tables.size() + " table(s) from Postgres schema [" + schema + "].");
        }

        merged.schemaName = schemaArg;
        merged.extractedAt = now();
        System.out.println("[INFO] Total tables across all schemas: " + merged.tables.size());

        reporter.write(merged, output);
    }

    // -------------------------------------------------------------------------
    // compare command
    // -------------------------------------------------------------------------

    private static void runCompare(Map<String, String> params, JsonReporter reporter) throws Exception {
        String entitiesFile = require(params, "entities");
        String oracleFile   = params.get("oracle");
        String postgresFile = params.get("postgres");
        String output       = params.getOrDefault("output", "report.json");

        System.out.println("[INFO] Loading entity schema from: " + entitiesFile);
        EntitySchema entitySchema = reporter.read(entitiesFile, EntitySchema.class);

        DbSchema oracleSchema = null;
        if (oracleFile != null) {
            System.out.println("[INFO] Loading Oracle schema from: " + oracleFile);
            oracleSchema = reporter.read(oracleFile, DbSchema.class);
        } else {
            System.out.println("[WARN] No Oracle schema file provided (--oracle). Oracle compatibility will show NOT_FOUND.");
            oracleSchema = emptyDbSchema("oracle");
        }

        DbSchema postgresSchema = null;
        if (postgresFile != null) {
            System.out.println("[INFO] Loading Postgres schema from: " + postgresFile);
            postgresSchema = reporter.read(postgresFile, DbSchema.class);
        } else {
            System.out.println("[WARN] No Postgres schema file provided (--postgres). Postgres compatibility will show NOT_FOUND.");
            postgresSchema = emptyDbSchema("postgres");
        }

        SchemaComparator comparator = new SchemaComparator();
        ComparisonReport report = comparator.compare(entitySchema, oracleSchema, postgresSchema);

        printSummary(report);
        reporter.write(report, output);
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private static void printSummary(ComparisonReport report) {
        ComparisonReport.Summary s = report.summary;
        System.out.println();
        System.out.println("===== COMPARISON SUMMARY =====");
        System.out.printf("  Entities:       %d%n", s.totalEntities);
        System.out.printf("  Columns:        %d%n", s.totalColumns);
        System.out.printf("  OK:             %d%n", s.ok);
        System.out.printf("  Warnings:       %d%n", s.warnings);
        System.out.printf("  Critical:       %d%n", s.criticalIssues);
        System.out.printf("  Not Found:      %d%n", s.notFound);
        System.out.println("==============================");
        System.out.println();

        // Print critical issues to console for quick visibility
        if (s.criticalIssues > 0) {
            System.out.println("CRITICAL ISSUES:");
            report.entities.forEach(entity ->
                entity.columns.stream()
                    .filter(c -> "CRITICAL".equals(c.overallStatus))
                    .forEach(c -> {
                        System.out.printf("  [%s] %s.%s (%s)%n",
                                entity.tableName, entity.entityClass, c.javaFieldName, c.javaType);
                        c.issues.forEach(issue -> System.out.println("    -> " + issue));
                    })
            );
            System.out.println();
        }
    }

    private static DbSchema emptyDbSchema(String type) {
        DbSchema s = new DbSchema();
        s.dbType = type;
        s.tables = Collections.emptyList();
        return s;
    }

    private static String require(Map<String, String> params, String key) {
        String val = params.get(key);
        if (val == null || val.isEmpty()) {
            System.err.println("[ERROR] Missing required parameter: --" + key);
            System.exit(1);
        }
        return val;
    }

    private static Map<String, String> parseArgs(String[] args, int start) {
        Map<String, String> map = new LinkedHashMap<>();
        for (int i = start; i < args.length - 1; i += 2) {
            String key = args[i].replaceFirst("^--", "");
            map.put(key, args[i + 1]);
        }
        return map;
    }

    private static String now() {
        return LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
    }

    private static void printHelp() {
        System.out.println("Entity-DB Comparator — detect type mismatches between Spring entities and Oracle/Postgres schemas");
        System.out.println();
        System.out.println("Usage:");
        System.out.println("  java -jar comparator-fat.jar entities  --source <src-path>  [--output entities.json]");
        System.out.println("  java -jar comparator-fat.jar oracle    --url <jdbc-url> --user <u> --pass <p> --schema <schema[,schema2,...]>  [--output oracle.json]");
        System.out.println("  java -jar comparator-fat.jar postgres  --url <jdbc-url> --user <u> --pass <p> [--schema public[,schema2,...]]  [--output postgres.json]");
        System.out.println("  java -jar comparator-fat.jar compare   --entities entities.json [--oracle oracle.json] [--postgres postgres.json] [--output report.json]");
        System.out.println();
        System.out.println("JDBC URL examples:");
        System.out.println("  Oracle:   jdbc:oracle:thin:@//host:1521/SERVICE_NAME");
        System.out.println("  Postgres: jdbc:postgresql://host:5432/dbname");
    }
}
