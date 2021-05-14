echo "Setting up database tables for RAFT"
sqlite3 server/raft.db < scripts/initialize_raft_db.sql

