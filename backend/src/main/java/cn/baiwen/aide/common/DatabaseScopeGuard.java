package cn.baiwen.aide.common;

import jakarta.annotation.PostConstruct;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Scope is fixed for this database; it must never silently switch through configuration. */
@Component
@DependsOn("flywayInitializer")
public class DatabaseScopeGuard {
    private final JdbcTemplate jdbc;
    private final AppProperties properties;
    public DatabaseScopeGuard(JdbcTemplate jdbc, AppProperties properties) { this.jdbc=jdbc; this.properties=properties; }
    @PostConstruct public void verify() {
        var comments=jdbc.queryForList("SELECT table_comment FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('shikigami','ranking_snapshot')",String.class);
        if (comments.size()!=2 || comments.stream().anyMatch(c -> !c.equals("bwp_scope:"+properties.scopeKey())))
            throw new IllegalStateException("数据库范围与 BWP_SCOPE_KEY 不一致，请使用独立数据库");
    }
}
