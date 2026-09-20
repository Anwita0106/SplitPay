-- Runs before schema.sql in docker-entrypoint-initdb.d (alphabetically first).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
