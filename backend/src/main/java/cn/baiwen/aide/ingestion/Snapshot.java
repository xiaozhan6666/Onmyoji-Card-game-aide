package cn.baiwen.aide.ingestion;

import java.time.LocalDateTime;
import java.util.UUID;

/** Internal persistence type; never serialized directly to the API. */
public class Snapshot {
    public Long id;
    public UUID captureId;
    public Long shikigamiId;
    public String seasonKey;
    public String playerId;
    public Integer grade;
    public Long bailianPoints;
    public Long cumulativeWins;
    public LocalDateTime capturedAt;
    public String sourceImageRef;

    public boolean sameObservation(Snapshot other) {
        return shikigamiId.equals(other.shikigamiId) && seasonKey.equals(other.seasonKey)
                && playerId.equals(other.playerId) && grade.equals(other.grade)
                && bailianPoints.equals(other.bailianPoints) && cumulativeWins.equals(other.cumulativeWins)
                && capturedAt.equals(other.capturedAt) && sourceImageRef.equals(other.sourceImageRef);
    }
}
