package cn.baiwen.aide.statistics;

import cn.baiwen.aide.ingestion.Snapshot;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface StatisticsMapper {
    @Select("SELECT id FROM shikigami ORDER BY id") List<Long> ids();
    @Select("SELECT name FROM shikigami WHERE id=#{id} FOR UPDATE") String lock(long id);
    @Select("""
        SELECT * FROM ranking_snapshot
        WHERE shikigami_id=#{id} AND captured_at >= #{start} AND captured_at <= #{end}
        ORDER BY player_id,captured_at,id
        """)
    List<Snapshot> observations(long id, LocalDateTime start, LocalDateTime end);
    @Update("""
        UPDATE shikigami SET sample_wins=#{report.wins},sample_losses=#{report.losses},
        period_start=#{report.periodStart},period_end=#{report.periodEnd},stats_updated_at=#{updated}
        WHERE id=#{id}
        """)
    void update(long id, StatisticsEngine.Report report, LocalDateTime updated);
}
