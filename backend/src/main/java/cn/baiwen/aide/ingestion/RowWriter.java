package cn.baiwen.aide.ingestion;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import cn.baiwen.aide.statistics.*;

@Service
public class RowWriter {
    private final SnapshotMapper mapper;
    private final StatisticsMapper statisticsMapper;
    private final StatisticsService statistics;
    public RowWriter(SnapshotMapper mapper, StatisticsMapper statisticsMapper, StatisticsService statistics) {
        this.mapper=mapper; this.statisticsMapper=statisticsMapper; this.statistics=statistics;
    }

    @Transactional(propagation=Propagation.REQUIRES_NEW, isolation=Isolation.READ_COMMITTED)
    public Map<String,Object> save(Snapshot row) {
        // Serialize writes and rebuilds for this shikigami, so late observations replace old intervals atomically.
        if (statisticsMapper.lock(row.shikigamiId) == null)
            return result(row.captureId.toString(), "invalid", null, "式神编号不存在");
        try {
            mapper.insert(row);
        } catch (DuplicateKeyException conflict) {
            var matches = mapper.findConflicts(row);
            if (matches.size() == 1 && matches.getFirst().sameObservation(row)) {
                var response = result(row.captureId.toString(), "duplicate", matches.getFirst().id, null);
                response.put("stored_capture_id", matches.getFirst().captureId.toString());
                return response;
            }
            return result(row.captureId.toString(), "conflict", matches.size()==1 ? matches.getFirst().id : null,
                    "采集编号或观察唯一键已存在，但业务字段或图片内容不同");
        }
        statistics.statistics(row.shikigamiId);
        return result(row.captureId.toString(), "saved", row.id, null);
    }

    public static Map<String,Object> result(String capture, String status, Long id, String reason) {
        var map=new LinkedHashMap<String,Object>();
        map.put("capture_id", capture); map.put("status", status);
        map.put("id", id == null ? null : id.toString()); map.put("reason", reason);
        return map;
    }
}
