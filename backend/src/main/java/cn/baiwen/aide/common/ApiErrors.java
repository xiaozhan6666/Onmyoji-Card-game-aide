package cn.baiwen.aide.common;

import java.util.Map;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;

@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler(ApiException.class)
    ResponseEntity<?> expected(ApiException e) { return ResponseEntity.status(e.status).body(Map.of("error", e.getMessage())); }
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<?> tooLarge(Exception e) { return ResponseEntity.status(413).body(Map.of("error", "上传超过大小限制")); }
    @ExceptionHandler(MissingServletRequestPartException.class)
    ResponseEntity<?> missing(Exception e) { return ResponseEntity.badRequest().body(Map.of("error", "缺少 manifest 或图片表单项")); }
    @ExceptionHandler(Exception.class)
    ResponseEntity<?> unexpected(Exception e) {
        LoggerFactory.getLogger(getClass()).error("请求处理失败", e);
        return ResponseEntity.status(503).body(Map.of("error", "服务暂时不可用；保留原 capture_id 后重试"));
    }
}
