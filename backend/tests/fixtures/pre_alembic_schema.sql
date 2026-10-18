-- The schema exactly as the pre-Alembic application created it (copied from the developer
-- database's sqlite_master on 2026-10-18). Schema only: it contains no data.
CREATE TABLE conversations (
	id VARCHAR(36) NOT NULL,
	project_id VARCHAR(36) NOT NULL,
	title VARCHAR(255) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);
CREATE TABLE messages (
	id VARCHAR(36) NOT NULL,
	conversation_id VARCHAR(36) NOT NULL,
	sender VARCHAR(32) NOT NULL,
	content TEXT NOT NULL,
	citations JSON NOT NULL,
	plan_steps JSON NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
);
CREATE TABLE project_files (
	id VARCHAR(36) NOT NULL,
	project_id VARCHAR(36) NOT NULL,
	file_path VARCHAR(1024) NOT NULL,
	file_name VARCHAR(255) NOT NULL,
	file_size_bytes INTEGER NOT NULL,
	language VARCHAR(64) NOT NULL,
	last_scanned_at DATETIME NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);
CREATE TABLE projects (
	id VARCHAR(36) NOT NULL,
	name VARCHAR(255) NOT NULL,
	description TEXT,
	root_path VARCHAR(1024) NOT NULL,
	is_indexed BOOLEAN NOT NULL,
	languages JSON NOT NULL,
	file_count INTEGER NOT NULL,
	last_indexed_at DATETIME,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);
