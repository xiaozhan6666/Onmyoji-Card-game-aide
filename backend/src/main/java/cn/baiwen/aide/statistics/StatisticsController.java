package cn.baiwen.aide.statistics;

import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class StatisticsController {
    private final StatisticsService service;
    public StatisticsController(StatisticsService service) { this.service=service; }
    @GetMapping("/api/rankings") public List<Map<String,Object>> rankings() { return service.rankings(); }
    @GetMapping("/api/shikigami/{id}/statistics") public Map<String,Object> statistics(@PathVariable long id) { return service.statistics(id); }
}
