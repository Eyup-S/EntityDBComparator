-- Oracle 19c schema extraction
-- Run this in SQL*Plus / SQL Developer / DBeaver and export the result as JSON or CSV.
-- Replace :schema with your schema/owner name (e.g. MYAPP).

SELECT
    c.table_name,
    c.column_name,
    c.data_type,
    c.char_length          AS character_max_length,
    c.data_precision       AS numeric_precision,
    c.data_scale           AS numeric_scale,
    c.nullable,
    c.data_default         AS column_default,
    c.column_id            AS ordinal_position,
    -- Computed: full type string for human-readable review
    c.data_type
    || CASE
         WHEN c.data_type IN ('VARCHAR2','NVARCHAR2','CHAR','NCHAR') THEN '(' || c.char_length || ')'
         WHEN c.data_type = 'NUMBER' AND c.data_precision IS NOT NULL AND c.data_scale IS NOT NULL
              THEN '(' || c.data_precision || ',' || c.data_scale || ')'
         WHEN c.data_type = 'NUMBER' AND c.data_precision IS NOT NULL
              THEN '(' || c.data_precision || ')'
         ELSE ''
       END                 AS full_data_type
FROM   all_tab_columns c
JOIN   all_tables t
       ON  t.owner      = c.owner
       AND t.table_name = c.table_name
WHERE  c.owner = UPPER('&schema')
ORDER  BY c.table_name, c.column_id;
