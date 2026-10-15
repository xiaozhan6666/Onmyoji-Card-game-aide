package cn.baiwen.aide.statistics;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** Exact reset estimate only; never inserts synthetic observations or differences across seasons. */
public final class SeasonResetCalculator {
    private SeasonResetCalculator() { }
    public record Result(BigDecimal exactPoints, long resetPoints) { }
    public static Result reset(long points) {
        if(points < 0) throw new IllegalArgumentException("百炼值不能为负");
        BigDecimal result=BigDecimal.valueOf(Math.min(points,1000));
        if(points > 1000) result=result.add(BigDecimal.valueOf(Math.min(points,3000)-1000).multiply(new BigDecimal("0.4")));
        if(points > 3000) result=result.add(BigDecimal.valueOf(points-3000).multiply(new BigDecimal("0.2")));
        result=result.stripTrailingZeros();
        return new Result(result, result.setScale(0,RoundingMode.FLOOR).longValueExact());
    }
}
