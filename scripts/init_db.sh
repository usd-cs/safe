echo "Setting up database tables for the SAFE"
sqlite3 server/safe.db < scripts/initialize_safe_db.sql

