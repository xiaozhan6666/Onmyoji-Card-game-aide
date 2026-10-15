package cn.baiwen.aide.ingestion;

import java.time.*;
import java.util.*;
import tools.jackson.databind.JsonNode;
import cn.baiwen.aide.common.ApiException;

public final class PayloadValidator {
    private PayloadValidator() {}
    public static void object(JsonNode node, String... fields) {
        if (node == null || !node.isObject()) throw ApiException.invalid("必须是 JSON 对象");
        Set<String> wanted=Set.of(fields);
        Set<String> actual=new HashSet<>();
        node.properties().forEach(entry -> actual.add(entry.getKey()));
        if (!actual.equals(wanted)) throw ApiException.invalid("字段缺失或包含未支持的字段");
    }
    public static String text(JsonNode node, String field) {
        var n=node.get(field);
        if (n == null || !n.isString()) throw ApiException.invalid(field+" 必须是字符串");
        return n.asString();
    }
    public static String identifier(JsonNode node, String field) {
        String value=text(node,field);
        if (value.isEmpty() || value.codePointCount(0,value.length())>64 || value.codePoints().anyMatch(
                c -> Character.isWhitespace(c) || Character.isSpaceChar(c) || Character.isISOControl(c) || Character.getType(c)==Character.FORMAT))
            throw ApiException.invalid(field+" 标识为空、过长或包含空白/控制字符");
        return value;
    }
    public static long number(JsonNode node, String field, long max, long min) {
        String value=text(node,field);
        if (!value.matches("0|[1-9][0-9]{0,18}")) throw ApiException.invalid(field+" 必须是规范十进制字符串");
        try {
            long number=Long.parseLong(value);
            if (number<min || number>max) throw new NumberFormatException();
            return number;
        } catch (NumberFormatException ex) { throw ApiException.invalid(field+" 超出允许范围"); }
    }
    public static List<String> imageKeys(JsonNode row) {
        var array=row.get("image_keys");
        if (array==null || !array.isArray() || array.isEmpty() || array.size()>8)
            throw ApiException.invalid("image_keys 必须包含 1–8 个图片标识");
        List<String> keys=new ArrayList<>();
        for (var value:array) {
            if (!value.isString() || !value.asString().matches("[A-Za-z0-9_-]{1,64}") || value.asString().equals("manifest"))
                throw ApiException.invalid("图片 key 格式错误或使用保留名称");
            if (keys.contains(value.asString())) throw ApiException.invalid("图片 key 重复");
            keys.add(value.asString());
        }
        return keys;
    }
    public static Snapshot snapshot(JsonNode row) {
        object(row,"capture_id","shikigami_id","season_key","player_id","grade","bailian_points","cumulative_wins","captured_at","image_keys");
        var out=new Snapshot();
        String capture=text(row,"capture_id");
        try {
            out.captureId=UUID.fromString(capture);
            if (!out.captureId.toString().equalsIgnoreCase(capture)) throw new IllegalArgumentException();
        } catch (IllegalArgumentException ex) { throw ApiException.invalid("capture_id 必须是标准 UUID"); }
        out.shikigamiId=number(row,"shikigami_id",4294967295L,1);
        out.seasonKey=identifier(row,"season_key"); out.playerId=identifier(row,"player_id");
        var grade=row.get("grade");
        if (!grade.isIntegralNumber() || !grade.canConvertToInt() || grade.asInt()<5 || grade.asInt()>10)
            throw ApiException.invalid("grade 必须是 5–10 的整数编码");
        out.grade=grade.asInt();
        out.bailianPoints=number(row,"bailian_points",Long.MAX_VALUE,0);
        out.cumulativeWins=number(row,"cumulative_wins",Long.MAX_VALUE,0);
        String timestamp=text(row,"captured_at");
        if (!timestamp.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{3}Z"))
            throw ApiException.invalid("captured_at 必须是 UTC 毫秒时间");
        try {
            // Parse a local datetime strictly, then treat it as UTC (no machine timezone).
            out.capturedAt=LocalDateTime.parse(timestamp.substring(0,timestamp.length()-1));
            if (out.capturedAt.getYear()<1000) throw new DateTimeException("MySQL DATETIME 下界");
        } catch (DateTimeException ex) { throw ApiException.invalid("captured_at 日期时间无效"); }
        imageKeys(row);
        return out;
    }
}
