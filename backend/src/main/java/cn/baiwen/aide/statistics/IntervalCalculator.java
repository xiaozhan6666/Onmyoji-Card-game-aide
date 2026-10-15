package cn.baiwen.aide.statistics;

import cn.baiwen.aide.ingestion.Snapshot;
import java.math.BigInteger;
import java.time.*;

public final class IntervalCalculator {
    private IntervalCalculator() { }
    public enum Reason {
        INFERRED, DIFFERENT_IDENTITY, CROSS_SEASON, INVALID_TIME, INTERVAL_TOO_LONG,
        RULES_UNCONFIRMED, OUTSIDE_RULE_PERIOD, UNKNOWN_GRADE, SCORING_GROUP_CHANGED,
        BELOW_RULE_MINIMUM, WINS_DECREASED, NEGATIVE_LOSSES, NON_INTEGER_LOSSES,
        NO_CHANGE, COUNTER_OVERFLOW, OTHER_SEASON
    }
    public record Result(Reason reason, long wins, long losses, String ruleVersion) {
        public boolean included() { return reason == Reason.INFERRED; }
    }
    static Result excluded(Reason reason, ScoreRules rules) { return new Result(reason,0,0,rules.version()); }
    public static Result calculate(Snapshot before, Snapshot after, ScoreRules rules, String scope, Duration maxInterval) {
        if(!before.shikigamiId.equals(after.shikigamiId) || !before.playerId.equals(after.playerId)) return excluded(Reason.DIFFERENT_IDENTITY,rules);
        if(!before.seasonKey.equals(after.seasonKey)) return excluded(Reason.CROSS_SEASON,rules);
        Duration elapsed=Duration.between(before.capturedAt,after.capturedAt);
        if(elapsed.isNegative() || elapsed.isZero()) return excluded(Reason.INVALID_TIME,rules);
        if(elapsed.compareTo(maxInterval) > 0) return excluded(Reason.INTERVAL_TOO_LONG,rules);
        if(!rules.ready(scope,before.seasonKey)) return excluded(Reason.RULES_UNCONFIRMED,rules);
        if(!rules.covers(before.capturedAt.toInstant(ZoneOffset.UTC),after.capturedAt.toInstant(ZoneOffset.UTC))) return excluded(Reason.OUTSIDE_RULE_PERIOD,rules);
        var first=rules.grades().get(before.grade); var last=rules.grades().get(after.grade);
        if(first == null || last == null) return excluded(Reason.UNKNOWN_GRADE,rules);
        if(!first.equals(last)) return excluded(Reason.SCORING_GROUP_CHANGED,rules);
        if(rules.minPoints() != null && (before.bailianPoints < rules.minPoints() || after.bailianPoints < rules.minPoints())) return excluded(Reason.BELOW_RULE_MINIMUM,rules);
        if(after.cumulativeWins < before.cumulativeWins) return excluded(Reason.WINS_DECREASED,rules);
        BigInteger wins=BigInteger.valueOf(after.cumulativeWins).subtract(BigInteger.valueOf(before.cumulativeWins));
        BigInteger delta=BigInteger.valueOf(after.bailianPoints).subtract(BigInteger.valueOf(before.bailianPoints));
        BigInteger numerator=wins.multiply(BigInteger.valueOf(first.win())).subtract(delta);
        if(numerator.signum() < 0) return excluded(Reason.NEGATIVE_LOSSES,rules);
        BigInteger[] division=numerator.divideAndRemainder(BigInteger.valueOf(first.loss()));
        if(division[1].signum() != 0) return excluded(Reason.NON_INTEGER_LOSSES,rules);
        if(wins.signum() == 0 && division[0].signum() == 0) return excluded(Reason.NO_CHANGE,rules);
        if(division[0].compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0) return excluded(Reason.COUNTER_OVERFLOW,rules);
        return new Result(Reason.INFERRED,wins.longValueExact(),division[0].longValueExact(),rules.version());
    }
}
