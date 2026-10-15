package cn.baiwen.aide.ingestion;

import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface SnapshotMapper {
    @Insert("""
        INSERT INTO ranking_snapshot(capture_id,shikigami_id,season_key,player_id,grade,bailian_points,cumulative_wins,captured_at,source_image_ref)
        VALUES(#{captureId},#{shikigamiId},#{seasonKey},#{playerId},#{grade},#{bailianPoints},#{cumulativeWins},#{capturedAt},#{sourceImageRef})
        """)
    @Options(useGeneratedKeys=true, keyProperty="id")
    void insert(Snapshot snapshot);

    @Select("""
        SELECT * FROM ranking_snapshot WHERE capture_id = #{captureId}
        OR (shikigami_id = #{shikigamiId} AND season_key = #{seasonKey} AND player_id = #{playerId} AND captured_at = #{capturedAt})
        FOR UPDATE
        """)
    List<Snapshot> findConflicts(Snapshot snapshot);
}
