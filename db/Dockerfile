# Postgres with the three extensions the schema needs:
# PostGIS (distance), pgvector (lookalike search), pg_trgm (fuzzy name matching, built in).
FROM postgis/postgis:16-3.4

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-pgvector \
 && rm -rf /var/lib/apt/lists/*

# Baked in rather than bind-mounted, so no host directory sharing is needed and
# every machine creates the same extensions on first start.
COPY init/ /docker-entrypoint-initdb.d/
