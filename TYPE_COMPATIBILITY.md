# Type Compatibility Rules

This document explains how EntityDBComparator classifies each Java field / database column pair as **OK**, **WARNING**, or **CRITICAL**.

---

## How it works

Every field is evaluated in two steps:

1. The Java type and the DB column type are each mapped to an abstract **category**.
2. The two categories are compared using the rules below.

---

## Java type categories

| Category | Java types |
|---|---|
| `STRING` | `String`, `char`, `Character`, `StringBuilder`, `StringBuffer`, `CharSequence` |
| `CLOB` | `String` / `CharSequence` with `@Lob` |
| `INTEGER` | `int`, `Integer`, `short`, `Short`, `AtomicInteger` |
| `LONG` | `long`, `Long`, `AtomicLong` |
| `DECIMAL` | `BigDecimal`, `BigInteger` |
| `FLOAT` | `float`, `Float`, `double`, `Double` |
| `BOOLEAN` | `boolean`, `Boolean` |
| `DATE` | `LocalDate`, `YearMonth` |
| `DATETIME` | `Date` (java.util.Date / java.sql.Date) |
| `TIMESTAMP` | `LocalDateTime`, `Timestamp`, `Calendar` |
| `TIMESTAMP_TZ` | `ZonedDateTime`, `OffsetDateTime`, `Instant` |
| `BLOB` | `byte[]` / `Byte[]` with `@Lob` |
| `BINARY` | `byte[]` / `Byte[]` without `@Lob` |
| `UUID` | `UUID` |
| `ENUM_STRING` | Any `enum` with `@Enumerated(STRING)` |
| `ENUM_ORDINAL` | Any `enum` with `@Enumerated(ORDINAL)` or no annotation |
| `UNKNOWN` | Anything else (custom types, unrecognized names) |

---

## DB type categories

### Oracle

| Category | Oracle types |
|---|---|
| `STRING` | `VARCHAR2`, `VARCHAR`, `CHAR`, `NVARCHAR2`, `NCHAR` |
| `CLOB` | `CLOB`, `NCLOB`, `LONG` |
| `INTEGER` | `NUMBER(p,0)` with precision ≤ 9, `INTEGER`, `SMALLINT`, `PLS_INTEGER`, `BINARY_INTEGER` |
| `LONG` | `NUMBER(p,0)` with precision 10–18 |
| `NUMERIC` | `NUMBER(p,s)` with scale > 0, unconstrained `NUMBER`, `NUMERIC`, `DECIMAL` |
| `FLOAT` | `FLOAT`, `BINARY_FLOAT`, `BINARY_DOUBLE`, `REAL` |
| `TIMESTAMP` | `DATE` *(Oracle DATE includes time)*, `TIMESTAMP`, `TIMESTAMP(n)` |
| `TIMESTAMP_TZ` | `TIMESTAMP WITH TIME ZONE`, `TIMESTAMP WITH LOCAL TIME ZONE` |
| `BLOB` | `BLOB`, `LONG RAW` |
| `BINARY` | `RAW` |
| `BOOLEAN` | `BOOLEAN` |
| `UNKNOWN` | `XMLTYPE`, `SDO_GEOMETRY`, `INTERVAL`, anything else |

### PostgreSQL

| Category | Postgres types |
|---|---|
| `STRING` | `CHARACTER VARYING`, `VARCHAR`, `CHARACTER`, `CHAR`, `BPCHAR`, `NAME`, `citext` |
| `CLOB` | `TEXT`, `XML` *(unbounded — closest equivalent to CLOB)* |
| `INTEGER` | `INTEGER`, `INT4`, `INT2`, `SMALLINT`, `SERIAL`, `SMALLSERIAL`, `NUMERIC(p,0)` with precision ≤ 9 |
| `LONG` | `BIGINT`, `INT8`, `BIGSERIAL`, `NUMERIC(p,0)` with precision 10–18 |
| `NUMERIC` | `NUMERIC`, `DECIMAL` with scale > 0, unconstrained `NUMERIC` |
| `FLOAT` | `REAL`, `FLOAT4`, `DOUBLE PRECISION`, `FLOAT8` |
| `BOOLEAN` | `BOOLEAN`, `BOOL` |
| `DATE` | `DATE` *(Postgres DATE has no time component)* |
| `TIMESTAMP` | `TIMESTAMP WITHOUT TIME ZONE`, `TIMESTAMP` |
| `TIMESTAMP_TZ` | `TIMESTAMP WITH TIME ZONE`, `TIMESTAMPTZ` |
| `BLOB` | `BYTEA`, `OID`, `LO` |
| `JSON` | `JSON`, `JSONB` |
| `UUID` | `UUID` |
| `UNKNOWN` | User-defined types not recognized, anything else |

---

## Compatibility rules

### Directly compatible (OK)

These pairs are always OK without further checks:

| Java category | Compatible DB categories |
|---|---|
| `STRING` | `STRING`, `JSON` |
| `CLOB` | `CLOB`, `STRING` |
| `INTEGER` | `INTEGER`, `LONG`, `NUMERIC` |
| `LONG` | `LONG`, `NUMERIC` |
| `DECIMAL` | `NUMERIC`, `LONG`, `INTEGER` |
| `FLOAT` | `FLOAT`, `NUMERIC` |
| `BOOLEAN` | `BOOLEAN` |
| `DATE` | `DATE` |
| `DATETIME` | `TIMESTAMP`, `DATE` |
| `TIMESTAMP` | `TIMESTAMP`, `TIMESTAMP_TZ` |
| `TIMESTAMP_TZ` | `TIMESTAMP_TZ`, `TIMESTAMP` |
| `BLOB` | `BLOB`, `BINARY` |
| `BINARY` | `BINARY`, `BLOB` |
| `UUID` | `UUID` |
| `ENUM_STRING` | `STRING` |
| `ENUM_ORDINAL` | `INTEGER`, `NUMERIC` |

---

### CRITICAL rules

A **CRITICAL** result means the mapping will likely throw a runtime error on PostgreSQL.

**String field → numeric column**
- Java `String` or `@Lob String` mapped to `INTEGER`, `LONG`, `NUMERIC`, or `FLOAT` column.
- Oracle silently casts `"123"` to a number; Postgres rejects any non-numeric value with a type error.

**Numeric Java type → string column**
- Java `int/long/BigDecimal/float/double` mapped to `STRING` or `CLOB` column.
- Likely a design mistake; Postgres rejects numeric writes into text columns without an explicit cast.

**`LocalDateTime` → Postgres `DATE`**
- Postgres `DATE` has no time component; the time part of every value is silently dropped on write.
- Use `TIMESTAMP` in Postgres instead.

**`@Enumerated(STRING)` → numeric column**
- The enum label (e.g. `"ACTIVE"`) cannot be stored in an integer column.
- Postgres rejects this with a type error.

---

### WARNING rules

A **WARNING** result means the mapping may work today but has a hidden risk or requires a converter/migration step.

**`Boolean` → string column**
- Typically a `Y`/`N` or `true`/`false` mapping using an `AttributeConverter`.
- Verify the converter is present and correct for Postgres.

**`Boolean` → integer/numeric column**
- Typically a `1`/`0` mapping.
- Verify this behaves correctly under Postgres.

**`LocalDate` → Oracle `DATE`**
- Oracle `DATE` stores both date and time. `LocalDate` has no time component, so the time part is silently lost on every read-back.
- Consider switching the column to `TIMESTAMP` on Oracle, or accept the loss.

**`@Enumerated(ORDINAL)` → string column**
- The enum ordinal (0, 1, 2…) is being stored in a text column.
- This is unusual and likely unintentional; verify with the team.

**Unknown type on either side**
- The Java type or DB type was not recognized.
- Manually check that the mapping is valid.

**Catch-all**
- Any combination not covered by the rules above and not directly compatible receives a WARNING.
- These need manual review.

---

## overallStatus vs per-DB status

Each field has three status values in the report:

- **`oracleCompatibility`** — result of checking the Java type against the Oracle column only.
- **`postgresCompatibility`** — result of checking the Java type against the Postgres column only.
- **`overallStatus`** — the worst of the two (CRITICAL > WARNING > NOT_FOUND > OK).

The viewer's status filters and color coding are all based on `overallStatus`.
