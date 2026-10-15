ALTER TABLE shikigami
    ADD COLUMN sample_games BIGINT UNSIGNED
    GENERATED ALWAYS AS (sample_wins + sample_losses) STORED
    COMMENT '统计窗口内有效观察区间的新增场数，非全服总场数'
    AFTER sample_losses;
