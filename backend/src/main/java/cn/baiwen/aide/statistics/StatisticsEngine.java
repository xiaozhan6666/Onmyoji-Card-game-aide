package cn.baiwen.aide.statistics;

import cn.baiwen.aide.ingestion.Snapshot;
import java.math.*;
import java.time.*;
import java.util.*;

public final class StatisticsEngine {
    private StatisticsEngine() { }
    public record Trace(String beforeId, String afterId, Integer beforeGrade, Integer afterGrade,
                        IntervalCalculator.Result calculation) { }
    public record GradeReport(Integer grade, String gradeName, String status, long wins, long losses,
                              int players, BigDecimal winRate, LocalDateTime periodStart,
                              LocalDateTime periodEnd, long intervalCount) { }
    public record Report(String status, long wins, long losses, int players, BigDecimal winRate,
                         LocalDateTime periodStart, LocalDateTime periodEnd,
                         Map<IntervalCalculator.Reason,Long> exclusions, List<Trace> intervals,
                         List<GradeReport> grades, GradeReport unassignedGrade) { }

    public static Report summarize(List<Snapshot> observations, ScoreRules rules, String scope,
                                   StatisticsProperties settings, Instant start, Instant end) {
        var rows=observations.stream().filter(row -> {
            var time=row.capturedAt.toInstant(ZoneOffset.UTC);
            return !time.isBefore(start) && !time.isAfter(end);
        }).sorted(Comparator.comparing((Snapshot row) -> row.playerId).thenComparing(row -> row.capturedAt)
                .thenComparing(row -> row.id, Comparator.nullsFirst(Comparator.naturalOrder()))).toList();
        var exclusions=new EnumMap<IntervalCalculator.Reason,Long>(IntervalCalculator.Reason.class);
        var traces=new ArrayList<Trace>();
        var total=new Accumulator(); var unassigned=new Accumulator();
        var grades=new TreeMap<Integer,Accumulator>();
        for(int grade=5;grade<=10;grade++) grades.put(grade,new Accumulator());
        Snapshot previous=null;
        for(Snapshot row:rows) {
            if(previous != null && previous.playerId.equals(row.playerId)) {
                var result=IntervalCalculator.calculate(previous,row,rules,scope,settings.maxInterval());
                if(!previous.seasonKey.equals(settings.seasonKey()) || !row.seasonKey.equals(settings.seasonKey())) {
                    result=IntervalCalculator.excluded(previous.seasonKey.equals(row.seasonKey)
                            ? IntervalCalculator.Reason.OTHER_SEASON : IntervalCalculator.Reason.CROSS_SEASON,rules);
                }
                traces.add(new Trace(id(previous),id(row),previous.grade,row.grade,result));
                if(result.included()) {
                    total.add(previous,row,result);
                    // Classify only after forming the full timeline. Filtering by grade first would bridge changes.
                    if(previous.grade.equals(row.grade)) grades.get(row.grade).add(previous,row,result);
                    else unassigned.add(previous,row,result);
                } else exclusions.merge(result.reason(),1L,Long::sum);
            }
            // An excluded observation is still the predecessor. Never bridge across it.
            previous=row;
        }
        String status=settings.seasonKey().isEmpty() ? "SEASON_UNCONFIRMED"
                : !rules.ready(scope,settings.seasonKey()) ? "RULES_UNCONFIRMED" : "READY";
        if(total.overflow()) status="COUNTER_OVERFLOW";
        var gradeReports=new ArrayList<GradeReport>();
        for(var entry:grades.entrySet()) gradeReports.add(entry.getValue().report(entry.getKey(),gradeName(entry.getKey()),status,settings.minimumGames()));
        var all=total.report(null,"全部",status,settings.minimumGames());
        return new Report(all.status(),all.wins(),all.losses(),all.players(),all.winRate(),all.periodStart(),all.periodEnd(),
                Map.copyOf(exclusions),List.copyOf(traces),List.copyOf(gradeReports),
                unassigned.report(null,"跨段位未分配",status,settings.minimumGames()));
    }
    private static String gradeName(int code) {
        return switch(code) { case 5 -> "五段"; case 6 -> "六段"; case 7 -> "七段"; case 8 -> "八段"; case 9 -> "名士"; case 10 -> "大名士"; default -> throw new IllegalArgumentException("未知段位"); };
    }
    private static final class Accumulator {
        BigInteger wins=BigInteger.ZERO, losses=BigInteger.ZERO;
        final Set<String> players=new HashSet<>();
        LocalDateTime first, last;
        long count;
        void add(Snapshot before, Snapshot after, IntervalCalculator.Result result) {
            wins=wins.add(BigInteger.valueOf(result.wins())); losses=losses.add(BigInteger.valueOf(result.losses()));
            players.add(after.playerId); count++;
            if(first == null || before.capturedAt.isBefore(first)) first=before.capturedAt;
            if(last == null || after.capturedAt.isAfter(last)) last=after.capturedAt;
        }
        boolean overflow() { return wins.bitLength()>63 || losses.bitLength()>63; }
        GradeReport report(Integer grade,String name,String status,long minimum) {
            if(status.equals("COUNTER_OVERFLOW")) return new GradeReport(grade,name,status,0,0,0,null,null,null,0);
            BigInteger games=wins.add(losses);
            if(status.equals("READY")) status=games.signum()==0 ? "NO_SAMPLES"
                    : games.compareTo(BigInteger.valueOf(minimum))<0 ? "INSUFFICIENT_SAMPLES" : "INFERRED";
            BigDecimal rate=status.equals("INFERRED") ? new BigDecimal(wins).divide(new BigDecimal(games),6,RoundingMode.HALF_UP) : null;
            return new GradeReport(grade,name,status,wins.longValueExact(),losses.longValueExact(),players.size(),rate,first,last,count);
        }
    }
    private static String id(Snapshot row) { return row.id == null ? null : row.id.toString(); }
}
