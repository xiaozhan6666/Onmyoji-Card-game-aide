package cn.baiwen.aide.statistics;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("bwp.statistics")
public record StatisticsProperties(String rulesResource, String seasonKey, Duration window,
                                   Duration maxInterval, long minimumGames) {
    public StatisticsProperties {
        if (rulesResource == null || rulesResource.isBlank() || seasonKey == null
                || (!seasonKey.isEmpty() && (!seasonKey.equals(seasonKey.strip()) || seasonKey.length() > 64))
                || window == null || window.isNegative() || window.isZero() || window.compareTo(Duration.ofDays(366)) > 0
                || maxInterval == null || maxInterval.isNegative() || maxInterval.isZero()
                || minimumGames < 1)
            throw new IllegalArgumentException("统计配置无效：窗口须在 0 到 366 天内，间隔和最小场数须为正数");
    }
}
