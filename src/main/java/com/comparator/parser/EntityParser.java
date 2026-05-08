package com.comparator.parser;

import com.comparator.model.EntityColumn;
import com.comparator.model.EntityInfo;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.*;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

public class EntityParser {

    static {
        StaticJavaParser.getParserConfiguration()
                .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_21);
    }

    /** Annotations that prevent a field from being a DB column */
    private static final Set<String> SKIP_ANNOTATIONS = new HashSet<>(Arrays.asList(
            "Transient", "OneToMany", "ManyToMany"
    ));

    /** Types that indicate a collection — skip these fields */
    private static final Set<String> COLLECTION_TYPES = new HashSet<>(Arrays.asList(
            "List", "Set", "Collection", "Map", "SortedSet", "SortedMap",
            "ArrayList", "HashSet", "LinkedList", "LinkedHashSet", "TreeSet"
    ));

    public List<EntityInfo> parseDirectory(String sourcePath) throws IOException {
        List<EntityInfo> results = new ArrayList<>();
        Path root = Paths.get(sourcePath);

        if (!Files.exists(root)) {
            throw new IllegalArgumentException("Source path does not exist: " + sourcePath);
        }

        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                if (file.toString().endsWith(".java")) {
                    try {
                        List<EntityInfo> parsed = parseFile(file);
                        results.addAll(parsed);
                    } catch (Exception e) {
                        System.err.println("[WARN] Failed to parse " + file + ": " + e.getMessage());
                    }
                }
                return FileVisitResult.CONTINUE;
            }
        });

        return results;
    }

    private List<EntityInfo> parseFile(Path file) throws IOException {
        List<EntityInfo> results = new ArrayList<>();
        CompilationUnit cu = StaticJavaParser.parse(file);

        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");

        cu.findAll(ClassOrInterfaceDeclaration.class).forEach(clazz -> {
            if (!isEntity(clazz)) return;

            EntityInfo entity = new EntityInfo();
            entity.className = clazz.getNameAsString();
            entity.fullClassName = packageName.isEmpty()
                    ? entity.className
                    : packageName + "." + entity.className;
            entity.filePath = file.toString();
            entity.tableName = resolveTableName(clazz);
            entity.columns = new ArrayList<>();

            clazz.getFields().forEach(field -> {
                if (shouldSkipField(field)) return;
                List<EntityColumn> cols = extractColumns(field);
                entity.columns.addAll(cols);
            });

            results.add(entity);
        });

        return results;
    }

    private boolean isEntity(ClassOrInterfaceDeclaration clazz) {
        return clazz.getAnnotationByName("Entity").isPresent()
                || clazz.getAnnotationByName("javax.persistence.Entity").isPresent()
                || clazz.getAnnotationByName("jakarta.persistence.Entity").isPresent();
    }

    private String resolveTableName(ClassOrInterfaceDeclaration clazz) {
        Optional<AnnotationExpr> tableAnn = clazz.getAnnotationByName("Table");
        if (!tableAnn.isPresent()) {
            tableAnn = clazz.getAnnotationByName("javax.persistence.Table");
        }
        if (!tableAnn.isPresent()) {
            tableAnn = clazz.getAnnotationByName("jakarta.persistence.Table");
        }

        if (tableAnn.isPresent()) {
            String name = getStringAttribute(tableAnn.get(), "name");
            if (name != null && !name.isEmpty()) return name;
        }

        // JPA default: class name as-is (Hibernate naming strategy may add underscores,
        // but we use the raw class name so the user can spot it)
        return clazz.getNameAsString().toUpperCase(java.util.Locale.ROOT);
    }

    private boolean shouldSkipField(FieldDeclaration field) {
        if (field.isStatic()) return true;

        for (String skip : SKIP_ANNOTATIONS) {
            if (field.getAnnotationByName(skip).isPresent()) return true;
        }

        // If it's a collection type without @JoinColumn, skip it
        boolean hasJoinColumn = field.getAnnotationByName("JoinColumn").isPresent();
        if (!hasJoinColumn) {
            String typeName = getSimpleTypeName(field);
            if (COLLECTION_TYPES.contains(typeName)) return true;
        }

        // Must have at least one of: @Column, @Id, @JoinColumn, @Lob
        boolean hasColumnAnnotation = field.getAnnotationByName("Column").isPresent()
                || field.getAnnotationByName("Id").isPresent()
                || field.getAnnotationByName("JoinColumn").isPresent()
                || field.getAnnotationByName("Lob").isPresent();

        return !hasColumnAnnotation;
    }

    private List<EntityColumn> extractColumns(FieldDeclaration field) {
        List<EntityColumn> columns = new ArrayList<>();

        boolean isLob = field.getAnnotationByName("Lob").isPresent();
        boolean isId = field.getAnnotationByName("Id").isPresent();
        boolean isJoinColumn = field.getAnnotationByName("JoinColumn").isPresent();

        boolean isEnumerated = field.getAnnotationByName("Enumerated").isPresent();
        String enumeratedType = "ORDINAL"; // default
        if (isEnumerated) {
            Optional<AnnotationExpr> enumAnn = field.getAnnotationByName("Enumerated");
            if (enumAnn.isPresent()) {
                String val = getEnumAttribute(enumAnn.get());
                if (val != null && val.contains("STRING")) enumeratedType = "STRING";
            }
        }

        String javaType = getSimpleTypeName(field);
        String rawJavaType = field.getVariables().isEmpty() ? javaType
                : field.getVariable(0).getTypeAsString();

        for (VariableDeclarator var : field.getVariables()) {
            EntityColumn col = new EntityColumn();
            col.fieldName = var.getNameAsString();
            col.javaType = javaType;
            col.rawJavaType = rawJavaType;
            col.isLob = isLob;
            col.isId = isId;
            col.isJoinColumn = isJoinColumn;
            col.isEnumerated = isEnumerated;
            col.enumeratedType = enumeratedType;

            if (isJoinColumn) {
                Optional<AnnotationExpr> jcAnn = field.getAnnotationByName("JoinColumn");
                col.columnName = jcAnn.map(a -> getStringAttribute(a, "name")).orElse(null);
                if (col.columnName == null || col.columnName.isEmpty()) {
                    col.columnName = col.fieldName.toUpperCase(java.util.Locale.ROOT) + "_ID";
                }
            } else {
                Optional<AnnotationExpr> colAnn = field.getAnnotationByName("Column");
                if (colAnn.isPresent()) {
                    String name = getStringAttribute(colAnn.get(), "name");
                    col.columnName = (name != null && !name.isEmpty()) ? name : col.fieldName;

                    String colDef = getStringAttribute(colAnn.get(), "columnDefinition");
                    if (colDef != null && !colDef.isEmpty()) col.columnDefinition = colDef;

                    Boolean nullableVal = getBooleanAttribute(colAnn.get(), "nullable");
                    col.nullable = (nullableVal == null) || nullableVal;
                } else {
                    col.columnName = col.fieldName;
                }
            }

            columns.add(col);
        }

        return columns;
    }

    // -------------------------------------------------------------------------
    // Annotation attribute helpers
    // -------------------------------------------------------------------------

    private String getStringAttribute(AnnotationExpr ann, String attrName) {
        if (ann instanceof NormalAnnotationExpr) {
            for (MemberValuePair pair : ((NormalAnnotationExpr) ann).getPairs()) {
                if (pair.getNameAsString().equals(attrName)) {
                    Expression val = pair.getValue();
                    if (val instanceof StringLiteralExpr) {
                        return ((StringLiteralExpr) val).asString();
                    }
                    return val.toString().replace("\"", "");
                }
            }
        } else if (ann instanceof SingleMemberAnnotationExpr && attrName.equals("value")) {
            Expression val = ((SingleMemberAnnotationExpr) ann).getMemberValue();
            if (val instanceof StringLiteralExpr) return ((StringLiteralExpr) val).asString();
            return val.toString().replace("\"", "");
        }
        return null;
    }

    private Boolean getBooleanAttribute(AnnotationExpr ann, String attrName) {
        if (ann instanceof NormalAnnotationExpr) {
            for (MemberValuePair pair : ((NormalAnnotationExpr) ann).getPairs()) {
                if (pair.getNameAsString().equals(attrName)) {
                    Expression val = pair.getValue();
                    if (val instanceof BooleanLiteralExpr) {
                        return ((BooleanLiteralExpr) val).getValue();
                    }
                    return Boolean.parseBoolean(val.toString());
                }
            }
        }
        return null;
    }

    private String getEnumAttribute(AnnotationExpr ann) {
        if (ann instanceof SingleMemberAnnotationExpr) {
            return ((SingleMemberAnnotationExpr) ann).getMemberValue().toString();
        }
        if (ann instanceof NormalAnnotationExpr) {
            for (MemberValuePair pair : ((NormalAnnotationExpr) ann).getPairs()) {
                if (pair.getNameAsString().equals("value")) {
                    return pair.getValue().toString();
                }
            }
        }
        return null;
    }

    private String getSimpleTypeName(FieldDeclaration field) {
        if (field.getVariables().isEmpty()) return "Unknown";
        String raw = field.getVariable(0).getTypeAsString();
        // Strip generics: "List<String>" -> "List"
        int lt = raw.indexOf('<');
        if (lt >= 0) raw = raw.substring(0, lt);
        // Strip array: "byte[]" -> "byte[]" (keep the [] marker)
        // Strip package: "java.lang.String" -> "String"
        int dot = raw.lastIndexOf('.');
        if (dot >= 0) raw = raw.substring(dot + 1);
        return raw.trim();
    }
}
