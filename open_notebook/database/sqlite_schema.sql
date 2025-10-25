-- SQLite schema for Open Notebook
-- This schema maps SurrealDB's graph database structure to SQLite relational tables

-- Core entity tables
CREATE TABLE IF NOT EXISTS notebook (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    archived INTEGER DEFAULT 0,  -- SQLite uses INTEGER for boolean
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS source (
    id TEXT PRIMARY KEY,
    asset_file_path TEXT,
    asset_url TEXT,
    title TEXT,
    topics TEXT,  -- JSON array stored as TEXT
    full_text TEXT,
    command TEXT,  -- RecordID reference stored as TEXT
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS source_embedding (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,  -- Foreign key to source.id
    "order" INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,  -- Store as JSON or binary
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (source) REFERENCES source(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_insight (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,  -- Foreign key to source.id
    insight_type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,  -- Store as JSON or binary
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (source) REFERENCES source(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS note (
    id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    note_type TEXT,  -- 'human' or 'ai'
    content TEXT,
    embedding BLOB,  -- Store as JSON or binary
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_session (
    id TEXT PRIMARY KEY,
    title TEXT,
    model_override TEXT,
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transformation (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    prompt TEXT,
    input_format TEXT,
    output_format TEXT,
    is_built_in INTEGER DEFAULT 0,
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS episode_profile (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    speakers TEXT,  -- JSON array
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS speaker_profile (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    voice_provider TEXT,
    voice_id TEXT,
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS episode (
    id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    profile TEXT,  -- Foreign key to episode_profile.id
    audio_file TEXT,
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

-- Relationship tables (mapping SurrealDB's RELATION TYPE to SQLite join tables)
-- SurrealDB: RELATION FROM source TO notebook
CREATE TABLE IF NOT EXISTS reference (
    id TEXT PRIMARY KEY,
    "in" TEXT NOT NULL,   -- source.id (quoted because 'in' is SQL keyword)
    "out" TEXT NOT NULL,  -- notebook.id
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now')),
    FOREIGN KEY ("in") REFERENCES source(id) ON DELETE CASCADE,
    FOREIGN KEY ("out") REFERENCES notebook(id) ON DELETE CASCADE,
    UNIQUE("in", "out")
);

-- SurrealDB: RELATION FROM note TO notebook
CREATE TABLE IF NOT EXISTS artifact (
    id TEXT PRIMARY KEY,
    "in" TEXT NOT NULL,   -- note.id
    "out" TEXT NOT NULL,  -- notebook.id
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now')),
    FOREIGN KEY ("in") REFERENCES note(id) ON DELETE CASCADE,
    FOREIGN KEY ("out") REFERENCES notebook(id) ON DELETE CASCADE,
    UNIQUE("in", "out")
);

-- Generic relationship table for other relations (like refers_to)
CREATE TABLE IF NOT EXISTS refers_to (
    id TEXT PRIMARY KEY,
    "in" TEXT NOT NULL,   -- source entity id
    "out" TEXT NOT NULL,  -- target entity id
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now')),
    UNIQUE("in", "out")
);

-- Configuration table (for singleton records like open_notebook:default_models)
CREATE TABLE IF NOT EXISTS config (
    id TEXT PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    value TEXT,  -- JSON value
    created TEXT DEFAULT (datetime('now')),
    updated TEXT DEFAULT (datetime('now'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_source_title ON source(title);
CREATE INDEX IF NOT EXISTS idx_source_updated ON source(updated);
CREATE INDEX IF NOT EXISTS idx_note_updated ON note(updated);
CREATE INDEX IF NOT EXISTS idx_notebook_updated ON notebook(updated);
CREATE INDEX IF NOT EXISTS idx_chat_session_updated ON chat_session(updated);

CREATE INDEX IF NOT EXISTS idx_source_embedding_source ON source_embedding(source);
CREATE INDEX IF NOT EXISTS idx_source_embedding_order ON source_embedding(source, "order");
CREATE INDEX IF NOT EXISTS idx_source_insight_source ON source_insight(source);

CREATE INDEX IF NOT EXISTS idx_reference_in ON reference("in");
CREATE INDEX IF NOT EXISTS idx_reference_out ON reference("out");
CREATE INDEX IF NOT EXISTS idx_artifact_in ON artifact("in");
CREATE INDEX IF NOT EXISTS idx_artifact_out ON artifact("out");
CREATE INDEX IF NOT EXISTS idx_refers_to_in ON refers_to("in");
CREATE INDEX IF NOT EXISTS idx_refers_to_out ON refers_to("out");

-- Full-text search support (SQLite FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS source_fts USING fts5(
    id UNINDEXED,
    title,
    full_text,
    content='source',
    content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(
    id UNINDEXED,
    title,
    content,
    content='note',
    content_rowid='rowid'
);

-- Triggers to keep FTS tables in sync
CREATE TRIGGER IF NOT EXISTS source_ai AFTER INSERT ON source BEGIN
    INSERT INTO source_fts(rowid, id, title, full_text)
    VALUES (new.rowid, new.id, new.title, new.full_text);
END;

CREATE TRIGGER IF NOT EXISTS source_ad AFTER DELETE ON source BEGIN
    DELETE FROM source_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS source_au AFTER UPDATE ON source BEGIN
    UPDATE source_fts SET title = new.title, full_text = new.full_text
    WHERE rowid = new.rowid;
END;

CREATE TRIGGER IF NOT EXISTS note_ai AFTER INSERT ON note BEGIN
    INSERT INTO note_fts(rowid, id, title, content)
    VALUES (new.rowid, new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS note_ad AFTER DELETE ON note BEGIN
    DELETE FROM note_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS note_au AFTER UPDATE ON note BEGIN
    UPDATE note_fts SET title = new.title, content = new.content
    WHERE rowid = new.rowid;
END;

-- Initialize default config if needed
INSERT OR IGNORE INTO config (id, key, value)
VALUES ('open_notebook:default_models', 'default_models', '{"default_chat_model": ""}');
