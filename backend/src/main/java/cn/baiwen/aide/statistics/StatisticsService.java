package cn.baiwen.aide.statistics;

import cn.baiwen.aide.common.*;
import java.math.BigInteger;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

@Service
public class StatisticsService {
    private final StatisticsMapper mapper;
    private final ScoreRules rules;
    private final StatisticsProperties settings;
    private final AppProperties app;
    private final Clock clock;
    public StatisticsService(StatisticsMapper mapper, ScoreRules rules, StatisticsProperties settings, AppProperties app, Clock clock) {
        this.mapper=mapper; this.rules=rules; this.settings=settings; this.app=app; this.clock=clock;
    }
    @Transactional(isolation=Isolation.READ_COMMITTED)
    public Map<String,Object> statistics(long id) { return refresh(id,clock.instant().truncatedTo(ChronoUnit.MILLIS)); }

    /** Small first release: rebuild on demand, including a rolling window with no new uploads. */
    @Transactional(isolation=Isolation.READ_COMMITTED)
    public List<Map<String,Object>> rankings() {
        Instant end=clock.instant().truncatedTo(ChronoUnit.MILLIS);
        var results=new ArrayList<Map<String,Object>>();
        for(long id:mapper.ids()) results.add(refresh(id,end));
        results.sort((a,b) -> {
            String left=(String)a.get("win_rate"), right=(String)b.get("win_rate");
            if(left == null) return right == null ? 0 : 1;
            if(right == null) return -1;
            return new java.math.BigDecimal(right).compareTo(new java.math.BigDecimal(left));
        });
        return results;
    }
    private Map<String,Object> refresh(long id, Instant end) {
        String name=mapper.lock(id);
        if(name == null) throw new ApiException(404,"式神不存在");
        Instant start=end.minus(settings.window());
        var observations=mapper.observations(id,utc(start),utc(end));
        var report=StatisticsEngine.summarize(observations,rules,app.scopeKey(),settings,start,end);
        mapper.update(id,report,utc(end));
        var result=new LinkedHashMap<String,Object>();
        result.put("id",Long.toString(id)); result.put("name",name); result.put("status",report.status());
        result.put("sample_wins",Long.toString(report.wins())); result.put("sample_losses",Long.toString(report.losses()));
        result.put("sample_games",BigInteger.valueOf(report.wins()).add(BigInteger.valueOf(report.losses())).toString());
        result.put("contributing_players",Integer.toString(report.players()));
        result.put("win_rate",report.winRate()==null ? null : report.winRate().toPlainString());
        result.put("period_start",timestamp(report.periodStart())); result.put("period_end",timestamp(report.periodEnd()));
        result.put("stats_updated_at",end.toString()); result.put("window_start",start.toString()); result.put("window_end",end.toString());
        result.put("scope_key",app.scopeKey()); result.put("season_key",settings.seasonKey());
        // Coverage is separate from inferred games. Keep only this season and
        // the same displayed window, with each player's most recent grade.
        var current=observations.stream().filter(s -> settings.seasonKey().equals(s.seasonKey)).toList();
        var latest=new HashMap<String,cn.baiwen.aide.ingestion.Snapshot>();
        for(var snapshot:current) latest.merge(snapshot.playerId,snapshot,
                (a,b) -> a.capturedAt.isAfter(b.capturedAt) ? a : b);
        result.put("observation_count",Integer.toString(current.size()));
        result.put("observed_players",Integer.toString(latest.size()));
        result.put("latest_capture_at",current.stream().map(s -> s.capturedAt).max(Comparator.naturalOrder())
                .map(StatisticsService::timestamp).orElse(null));
        var coverage=new ArrayList<Map<String,Object>>();
        for(int grade=5;grade<=10;grade++) {
            int selected=grade;
            coverage.add(Map.of("grade",grade,"player_count",Long.toString(latest.values().stream().filter(s -> s.grade==selected).count())));
        }
        result.put("latest_observed_grades",coverage);
        result.put("rule_version",rules.version()); result.put("rule_sha256",rules.sha256());
        result.put("calculation_mode",rules.calculationMode()); result.put("conditions_confirmed",rules.conditionsConfirmed());
        result.put("observation_start",rules.from()==null ? null : rules.from().toString());
        result.put("grade_statistics",report.grades().stream().map(StatisticsService::gradeResult).toList());
        result.put("unassigned_grade",gradeResult(report.unassignedGrade()));
        result.put("minimum_games",Long.toString(settings.minimumGames())); result.put("max_interval_seconds",Long.toString(settings.maxInterval().toSeconds()));
        var reasons=new TreeMap<String,String>(); report.exclusions().forEach((reason,count) -> reasons.put(reason.name(),count.toString()));
        result.put("excluded_intervals",reasons);
        result.put("method","从首次观察建立基线，按新增胜场与积分变化推算；按段位统计假设期间段位未变、无额外加扣分。跨段位同计分组区间单列未分配，不能代表全体玩家胜率");
        return result;
    }
    private static Map<String,Object> gradeResult(StatisticsEngine.GradeReport report) {
        var result=new LinkedHashMap<String,Object>();
        result.put("grade",report.grade()); result.put("grade_name",report.gradeName()); result.put("status",report.status());
        result.put("sample_wins",Long.toString(report.wins())); result.put("sample_losses",Long.toString(report.losses()));
        result.put("sample_games",BigInteger.valueOf(report.wins()).add(BigInteger.valueOf(report.losses())).toString());
        result.put("contributing_players",Integer.toString(report.players())); result.put("interval_count",Long.toString(report.intervalCount()));
        result.put("win_rate",report.winRate()==null ? null : report.winRate().toPlainString());
        result.put("period_start",timestamp(report.periodStart())); result.put("period_end",timestamp(report.periodEnd()));
        return result;
    }
    private static LocalDateTime utc(Instant instant) { return LocalDateTime.ofInstant(instant,ZoneOffset.UTC); }
    private static String timestamp(LocalDateTime time) { return time == null ? null : time.toInstant(ZoneOffset.UTC).toString(); }
}
