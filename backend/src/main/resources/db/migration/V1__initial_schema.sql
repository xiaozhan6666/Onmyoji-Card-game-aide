CREATE TABLE shikigami (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    sample_wins BIGINT UNSIGNED NOT NULL DEFAULT 0,
    sample_losses BIGINT UNSIGNED NOT NULL DEFAULT 0,
    win_rate DECIMAL(9,6) GENERATED ALWAYS AS (
        CAST(sample_wins AS DECIMAL(30,6)) /
        NULLIF(CAST(sample_wins AS DECIMAL(30,6)) + CAST(sample_losses AS DECIMAL(30,6)), 0)
    ) STORED,
    period_start DATETIME(3) NULL,
    period_end DATETIME(3) NULL,
    stats_updated_at DATETIME(3) NULL,
    CONSTRAINT ck_sample_wins CHECK (sample_wins <= 9223372036854775807),
    CONSTRAINT ck_sample_losses CHECK (sample_losses <= 9223372036854775807)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='bwp_scope:${scopeKey}';

CREATE TABLE ranking_snapshot (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    capture_id BINARY(16) NOT NULL,
    shikigami_id INT UNSIGNED NOT NULL,
    season_key VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
    player_id VARCHAR(64) COLLATE utf8mb4_0900_bin NOT NULL,
    grade TINYINT UNSIGNED NOT NULL,
    bailian_points BIGINT UNSIGNED NOT NULL,
    cumulative_wins BIGINT UNSIGNED NOT NULL,
    captured_at DATETIME(3) NOT NULL,
    source_image_ref TEXT NOT NULL,
    UNIQUE KEY uk_capture (capture_id),
    UNIQUE KEY uk_observation (shikigami_id, season_key, player_id, captured_at),
    CONSTRAINT fk_snapshot_shikigami FOREIGN KEY (shikigami_id) REFERENCES shikigami(id),
    CONSTRAINT ck_grade CHECK (grade IN (5,6,7,8,9,10)),
    CONSTRAINT ck_bailian_points CHECK (bailian_points <= 9223372036854775807),
    CONSTRAINT ck_cumulative_wins CHECK (cumulative_wins <= 9223372036854775807)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='bwp_scope:${scopeKey}';
