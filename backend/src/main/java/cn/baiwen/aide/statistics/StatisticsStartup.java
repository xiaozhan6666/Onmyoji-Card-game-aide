package cn.baiwen.aide.statistics;

import org.springframework.boot.*;
import org.springframework.context.annotation.DependsOn;
import org.springframework.stereotype.Component;

@Component
@DependsOn("databaseScopeGuard")
public class StatisticsStartup implements ApplicationRunner {
    private final StatisticsService service;
    public StatisticsStartup(StatisticsService service) { this.service=service; }
    @Override public void run(ApplicationArguments arguments) { service.rankings(); }
}
