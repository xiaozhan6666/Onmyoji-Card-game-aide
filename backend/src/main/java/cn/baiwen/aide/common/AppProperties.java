package cn.baiwen.aide.common;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("bwp")
public record AppProperties(String scopeKey, String collectorToken, Path storageRoot) {
    public AppProperties {
        if (scopeKey == null || !scopeKey.matches("[A-Za-z0-9_-]{1,64}"))
            throw new IllegalArgumentException("BWP_SCOPE_KEY 必须是 1–64 位字母、数字、下划线或短横线");
        if (collectorToken == null || collectorToken.length() < 32)
            throw new IllegalArgumentException("BWP_COLLECTOR_TOKEN 至少需要 32 个字符");
        if (storageRoot == null) throw new IllegalArgumentException("必须配置图片目录");
    }
}
