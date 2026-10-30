-- DataPulse PostgreSQL Initialization Script
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create warehouse schema
CREATE SCHEMA IF NOT EXISTS warehouse;
GRANT ALL ON SCHEMA warehouse TO datapulse;
