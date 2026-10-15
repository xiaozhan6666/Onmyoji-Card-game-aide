package cn.baiwen.aide.statistics;

import java.io.IOException;
import java.time.Clock;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ResourceLoader;

@Configuration
public class StatisticsConfiguration {
    @Bean Clock statisticsClock() { return Clock.systemUTC(); }
    @Bean ScoreRules scoreRules(StatisticsProperties properties, ResourceLoader loader) throws IOException {
        try (var input=loader.getResource(properties.rulesResource()).getInputStream()) { return ScoreRules.read(input); }
    }
}
