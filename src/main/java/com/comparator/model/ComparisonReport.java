package com.comparator.model;

import java.util.List;

public class ComparisonReport {
    public String generatedAt;
    public Summary summary;
    public List<ComparisonEntity> entities;

    public static class Summary {
        public int totalEntities;
        public int totalColumns;
        public int criticalIssues;
        public int warnings;
        public int notFound;
        public int ok;
    }
}
