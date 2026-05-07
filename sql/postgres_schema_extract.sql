-- PostgreSQL schema extraction
-- Run this in psql / DBeaver / pgAdmin and export the result.
-- Replace 'public' with your actual schema name.

SELECT
    c.table_name,
    c.column_name,
    c.data_type,
    c.character_maximum_length,
    c.numeric_precision,
    c.numeric_scale,
    c.is_nullable,
    c.column_default,
    c.udt_name,
    c.ordinal_position,
    -- Full type for human-readable review
    CASE
        WHEN c.data_type = 'character varying' AND c.character_maximum_length IS NOT NULL
             THEN 'varchar(' || c.character_maximum_length || ')'
        WHEN c.data_type = 'numeric' AND c.numeric_precision IS NOT NULL AND c.numeric_scale IS NOT NULL
             THEN 'numeric(' || c.numeric_precision || ',' || c.numeric_scale || ')'
        WHEN c.data_type = 'numeric' AND c.numeric_precision IS NOT NULL
             THEN 'numeric(' || c.numeric_precision || ')'
        ELSE c.data_type
    END AS full_data_type
FROM   information_schema.columns c
JOIN   information_schema.tables t
       ON  t.table_schema = c.table_schema
       AND t.table_name   = c.table_name
WHERE  c.table_schema = 'public'          -- change to your schema
  AND  t.table_type   = 'BASE TABLE'
ORDER  BY c.table_name, c.ordinal_position;
