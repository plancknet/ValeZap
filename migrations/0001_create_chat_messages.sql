CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY,
    session_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    message TEXT NOT NULL,
    is_from_user BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_player
    ON chat_messages (session_id, player_id, created_at);