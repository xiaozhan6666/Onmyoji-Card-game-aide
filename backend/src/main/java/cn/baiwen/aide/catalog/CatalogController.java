package cn.baiwen.aide.catalog;

import java.util.*;
import org.springframework.web.bind.annotation.*;
import cn.baiwen.aide.statistics.StatisticsService;

@RestController
public class CatalogController {
    private final StatisticsService statistics;
    public CatalogController(StatisticsService statistics) { this.statistics=statistics; }
    @GetMapping("/api/health") public Map<String,String> health() { return Map.of("status","ok","stage","4"); }
    @GetMapping("/api/shikigami") public List<Map<String,Object>> catalog() {
        return statistics.rankings().stream().sorted(Comparator.comparingLong(row -> Long.parseLong((String)row.get("id")))).toList();
    }
}
