package cn.baiwen.aide.ingestion;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import cn.baiwen.aide.common.*;
import static cn.baiwen.aide.ingestion.PayloadValidator.*;

@RestController
public class IngestionController {
    private final AppProperties properties;
    private final ImageStorage storage;
    private final RowWriter writer;
    private final JsonMapper json=JsonMapper.builder().enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build();
    public IngestionController(AppProperties properties, ImageStorage storage, RowWriter writer) {
        this.properties=properties; this.storage=storage; this.writer=writer;
    }
    @PostMapping(value="/api/collector/batches",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String,Object> upload(@RequestPart("manifest") String manifest, MultipartHttpServletRequest request) throws Exception {
        if (manifest.getBytes(StandardCharsets.UTF_8).length>256*1024) throw ApiException.invalid("manifest 超过 256 KiB");
        JsonNode batch;
        try { batch=json.readTree(manifest); }
        catch (RuntimeException e) { throw ApiException.invalid("manifest 不是合法 JSON 或包含重复字段"); }
        object(batch,"schema_version","scope_key","records","images");
        if (!"1.0".equals(text(batch,"schema_version"))) throw ApiException.invalid("不支持的 schema_version");
        if (!properties.scopeKey().equals(identifier(batch,"scope_key"))) throw ApiException.invalid("scope_key 与数据库固定范围不符");
        var records=batch.get("records"); var imageList=batch.get("images");
        if (!records.isArray() || records.isEmpty() || records.size()>100) throw ApiException.invalid("每批需要 1–100 条记录");
        if (!imageList.isArray() || imageList.isEmpty() || imageList.size()>8) throw ApiException.invalid("每批需要 1–8 张图片");
        var images=new LinkedHashMap<String,ImageStorage.CheckedImage>();
        for (var image:imageList) {
            object(image,"key","sha256");
            String key=text(image,"key"),sha=text(image,"sha256");
            if (!key.matches("[A-Za-z0-9_-]{1,64}") || key.equals("manifest") || images.containsKey(key))
                throw ApiException.invalid("图片 key 无效、重复或使用保留名称");
            if (!sha.matches("[0-9a-f]{64}")) throw ApiException.invalid("图片 sha256 格式错误");
            var files=request.getFiles(key);
            if (files.size()!=1) throw ApiException.invalid("每个图片 key 必须对应一个文件");
            images.put(key,storage.check(files.getFirst(),sha));
        }
        long manifests=request.getParts().stream().filter(p -> p.getName().equals("manifest")).count();
        if (manifests!=1 || request.getParts().stream().anyMatch(p -> !p.getName().equals("manifest") && !images.containsKey(p.getName())))
            throw ApiException.invalid("包含重复 manifest 或未声明的表单项");
        List<Map<String,Object>> results=new ArrayList<>();
        int index=0;
        for (var row:records) {
            String capture=row.path("capture_id").isString() ? row.path("capture_id").asString() : null;
            Map<String,Object> response;
            try {
                var snapshot=snapshot(row);
                var keys=imageKeys(row);
                if (!images.keySet().containsAll(keys)) throw ApiException.invalid("记录引用了未上传的图片");
                snapshot.sourceImageRef=storage.persist(keys.stream().map(images::get).toList());
                // A separate Spring bean ensures transaction advice runs and commits before success is returned.
                response=writer.save(snapshot);
            } catch (ApiException e) { response=RowWriter.result(capture,"invalid",null,e.getMessage()); }
            response.put("record_index",index++);
            results.add(response);
        }
        return Map.of("schema_version","1.0","results",results);
    }
}
