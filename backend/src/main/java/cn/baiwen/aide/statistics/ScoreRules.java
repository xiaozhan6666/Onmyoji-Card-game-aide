package cn.baiwen.aide.statistics;

import java.io.*;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.Instant;
import java.util.*;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/** Immutable rule version. Missing applicability information never becomes an implicit default. */
public record ScoreRules(String version, String source, String sha256, String scopeKey, Set<String> seasons,
                         boolean conditionsConfirmed, Long minPoints, Instant from, Instant to,
                         Map<Integer, Points> grades, String calculationMode) {
    public record Points(long win, long loss) { }
    public boolean ready(String scope, String season) {
        return (calculationMode.equals("observation") || (conditionsConfirmed && minPoints != null))
                && from != null && scope.equals(scopeKey)
                && seasons.contains(season);
    }
    public boolean covers(Instant start, Instant end) {
        return from != null && !start.isBefore(from) && (to == null || end.isBefore(to));
    }
    public static ScoreRules read(InputStream input) throws IOException {
        byte[] bytes=input.readNBytes(65537);
        if (bytes.length > 65536) throw new IllegalArgumentException("计分配置超过 64 KiB");
        var options=new LoaderOptions(); options.setAllowDuplicateKeys(false); options.setMaxAliasesForCollections(0);
        Object loaded=new Yaml(new SafeConstructor(options)).load(new String(bytes, StandardCharsets.UTF_8));
        Map<?,?> root=object(loaded);
        keys(root, Set.of("version","source","scope_key","season_keys","conditions_confirmed","min_points","effective_from","effective_to","rules","calculation_mode"));
        String mode=root.containsKey("calculation_mode") ? requiredText(root.get("calculation_mode")) : "confirmed";
        if(!Set.of("confirmed","observation").contains(mode)) throw new IllegalArgumentException("未知 calculation_mode");
        String version=requiredText(root.get("version")), source=requiredText(root.get("source"));
        String scope=optionalText(root.get("scope_key"));
        var seasons=new HashSet<String>();
        if (!(root.get("season_keys") instanceof List<?> seasonList)) throw new IllegalArgumentException("season_keys 必须为列表");
        for (var season:seasonList) if(!seasons.add(requiredText(season))) throw new IllegalArgumentException("重复赛季");
        if (!(root.get("conditions_confirmed") instanceof Boolean confirmed)) throw new IllegalArgumentException("conditions_confirmed 必须为布尔值");
        Long min=root.get("min_points")==null ? null : integer(root.get("min_points"));
        if (min != null && min < 0) throw new IllegalArgumentException("min_points 不能为负");
        Instant from=time(root.get("effective_from")), to=time(root.get("effective_to"));
        if (to != null && (from == null || !to.isAfter(from))) throw new IllegalArgumentException("规则有效期无效");
        var groups=new HashMap<Integer,Points>();
        if (!(root.get("rules") instanceof List<?> rules) || rules.isEmpty()) throw new IllegalArgumentException("rules 不能为空");
        for (Object value:rules) {
            Map<?,?> rule=object(value); keys(rule, Set.of("grades","win_points","loss_points"));
            long win=integer(rule.get("win_points")), loss=integer(rule.get("loss_points"));
            if(win <= 0 || loss >= 0 || loss == Long.MIN_VALUE) throw new IllegalArgumentException("胜分须为正，负分须为负");
            if (!(rule.get("grades") instanceof List<?> codes) || codes.isEmpty()) throw new IllegalArgumentException("grades 不能为空");
            for(Object code:codes) {
                long grade=integer(code);
                if(grade < 5 || grade > 10 || groups.putIfAbsent((int)grade,new Points(win,-loss)) != null)
                    throw new IllegalArgumentException("段位未知或重复");
            }
        }
        if(confirmed && (scope == null || seasons.isEmpty() || min == null || from == null))
            throw new IllegalArgumentException("确认规则前须补齐范围、赛季、积分下限和生效时间");
        if(mode.equals("observation") && (scope == null || seasons.isEmpty() || from == null))
            throw new IllegalArgumentException("观察推算须指定范围、赛季和观察起点");
        try {
            String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
            return new ScoreRules(version,source,hash,scope,Set.copyOf(seasons),confirmed,min,from,to,Map.copyOf(groups),mode);
        } catch(NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    private static Map<?,?> object(Object value) {
        if(value instanceof Map<?,?> map) return map;
        throw new IllegalArgumentException("计分配置必须是对象");
    }
    private static void keys(Map<?,?> map, Set<String> allowed) {
        if(!allowed.containsAll(map.keySet())) throw new IllegalArgumentException("计分配置包含未知字段");
    }
    private static String requiredText(Object value) {
        if(value instanceof String text && !text.isBlank() && text.equals(text.strip())) return text;
        throw new IllegalArgumentException("配置文本缺失或无效；时间请使用带引号的 UTC ISO 字符串");
    }
    private static String optionalText(Object value) { return value == null ? null : requiredText(value); }
    private static Instant time(Object value) { return value == null ? null : Instant.parse(requiredText(value)); }
    private static long integer(Object value) {
        if(value instanceof Byte || value instanceof Short || value instanceof Integer || value instanceof Long) return ((Number)value).longValue();
        if(value instanceof BigInteger number) return number.longValueExact();
        throw new IllegalArgumentException("计分字段必须为整数");
    }
}
