CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 64),
    path TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL CHECK (
        content_type IN ('image/jpeg', 'image/png', 'image/gif', 'image/webp')
    )
);
