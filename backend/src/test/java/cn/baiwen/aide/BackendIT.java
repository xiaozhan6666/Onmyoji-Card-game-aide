package cn.baiwen.aide;

import java.awt.image.BufferedImage;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MySQLContainer;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import cn.baiwen.aide.ingestion.ImageStorage;
import cn.baiwen.aide.statistics.StatisticsService;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT)
class BackendIT {
    @TestConfiguration static class FixedClock {
        @Bean @Primary Clock fixedStatisticsClock() { return Clock.fixed(Instant.parse("2026-10-13T20:00:00Z"),ZoneOffset.UTC); }
    }
    static final String TOKEN="stage3-test-token-not-for-production-1234567890";
    static final JsonMapper JSON=JsonMapper.builder().build();
    static final HttpClient CLIENT=HttpClient.newHttpClient();
    static final Path STORAGE=createStorage();
    static MySQLContainer<?> container;
    static Path createStorage() {
        try { return Files.createTempDirectory("bwp-stage3-images-"); }
        catch(IOException e) { throw new UncheckedIOException(e); }
    }
    @DynamicPropertySource static void properties(DynamicPropertyRegistry r) {
        String url=System.getenv("BWP_TEST_DB_URL");
        if (url==null || url.isBlank()) {
            container=new MySQLContainer<>("mysql:8.4.11").withDatabaseName("bwp_stage3_test_container");
            container.start();
            r.add("spring.datasource.url", () -> container.getJdbcUrl()+(container.getJdbcUrl().contains("?") ? "&" : "?")+"connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true");
            r.add("spring.datasource.username",container::getUsername); r.add("spring.datasource.password",container::getPassword);
        } else {
            // Never clean or exercise a developer's real database by accident.
            if (!url.matches("jdbc:mysql://[^/]+/bwp_stage3_test_[a-z0-9]+(?:\\?.*)?"))
                throw new IllegalArgumentException("测试库名称必须以 bwp_stage3_test_ 开头");
            r.add("spring.datasource.url", () -> url);
            r.add("spring.datasource.username", () -> System.getenv("BWP_TEST_DB_USER"));
            r.add("spring.datasource.password", () -> System.getenv("BWP_TEST_DB_PASSWORD"));
        }
        r.add("bwp.scope-key", () -> "integration-test");
        r.add("spring.flyway.placeholders.scopeKey", () -> "integration-test");
        r.add("bwp.collector-token", () -> TOKEN);
        r.add("bwp.storage-root", () -> STORAGE.toString());
        r.add("bwp.statistics.rules-resource", () -> "classpath:rules-test.yaml");
        r.add("bwp.statistics.season-key", () -> "test-season");
    }
    @Autowired JdbcTemplate jdbc;
    @Autowired StatisticsService statistics;
    @LocalServerPort int port;
    byte[] image;
    @BeforeEach void setup() throws Exception {
        jdbc.execute("DROP TRIGGER IF EXISTS fail_snapshot");
        jdbc.execute("DROP TRIGGER IF EXISTS fail_statistics");
        jdbc.update("DELETE FROM ranking_snapshot");
        jdbc.update("UPDATE shikigami SET sample_wins=0,sample_losses=0,period_start=NULL,period_end=NULL,stats_updated_at=NULL");
        var pixels=new BufferedImage(20,10,BufferedImage.TYPE_INT_RGB);
        var out=new ByteArrayOutputStream(); ImageIO.write(pixels,"png",out); image=out.toByteArray();
    }
    @AfterAll static void stopContainer() { if(container!=null) container.stop(); }
    Map<String,Object> row() {
        var r=new LinkedHashMap<String,Object>();
        r.put("capture_id",UUID.randomUUID().toString()); r.put("shikigami_id","1"); r.put("season_key","test-season");
        r.put("player_id","000123"); r.put("grade",5); r.put("bailian_points","1840"); r.put("cumulative_wins","100");
        r.put("captured_at","2026-10-13T12:00:00.123Z"); r.put("image_keys",List.of("board")); return r;
    }
    Map<String,Object> batch(List<Map<String,Object>> rows) {
        return new LinkedHashMap<>(Map.of("schema_version","1.0","scope_key","integration-test","records",rows,
                "images",List.of(Map.of("key","board","sha256",ImageStorage.hash(image)))));
    }
    HttpResponse<String> send(Map<String,Object> body, Map<String,byte[]> files, boolean authorized) throws Exception {
        String boundary="bwp-"+UUID.randomUUID(); var out=new ByteArrayOutputStream();
        out.write(("--"+boundary+"\r\nContent-Disposition: form-data; name=\"manifest\"\r\nContent-Type: application/json\r\n\r\n"+JSON.writeValueAsString(body)+"\r\n").getBytes(StandardCharsets.UTF_8));
        for(var file:files.entrySet()) {
            out.write(("--"+boundary+"\r\nContent-Disposition: form-data; name=\""+file.getKey()+"\"; filename=\"../../unsafe-name.png\"\r\nContent-Type: image/png\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            out.write(file.getValue()); out.write("\r\n".getBytes(StandardCharsets.UTF_8));
        }
        out.write(("--"+boundary+"--\r\n").getBytes(StandardCharsets.UTF_8));
        var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/collector/batches"))
                .timeout(Duration.ofSeconds(30)).header("Content-Type","multipart/form-data; boundary="+boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(out.toByteArray()));
        if(authorized) request.header("Authorization","Bearer "+TOKEN);
        return CLIENT.send(request.build(),HttpResponse.BodyHandlers.ofString());
    }
    JsonNode upload(Map<String,Object> row) throws Exception {
        var response=send(batch(List.of(row)),Map.of("board",image),true);
        assertEquals(200,response.statusCode(),response.body()); return JSON.readTree(response.body()).path("results").get(0);
    }
    int count() { return jdbc.queryForObject("SELECT COUNT(*) FROM ranking_snapshot",Integer.class); }

    @Test void savesImageReferenceUuidAndUtcTimestamp() throws Exception {
        var row=row(); var result=upload(row); assertEquals("saved",result.path("status").asString()); assertTrue(result.path("id").isString());
        assertEquals("000123",jdbc.queryForObject("SELECT player_id FROM ranking_snapshot",String.class));
        assertEquals(row.get("capture_id"),jdbc.queryForObject("SELECT BIN_TO_UUID(capture_id,0) FROM ranking_snapshot",String.class));
        assertEquals(LocalDateTime.parse("2026-10-13T12:00:00.123"),jdbc.queryForObject("SELECT captured_at FROM ranking_snapshot",LocalDateTime.class));
        String ref=jdbc.queryForObject("SELECT source_image_ref FROM ranking_snapshot",String.class);
        assertTrue(Files.exists(STORAGE.resolve(ref))); assertFalse(ref.contains("unsafe"));
        assertEquals(1,count());
    }
    @Test void retriesDoNotOverwriteOrDuplicate() throws Exception {
        var row=row(); var first=upload(row); var retry=upload(row);
        assertEquals("duplicate",retry.path("status").asString()); assertEquals(first.path("id"),retry.path("id"));
        row.put("bailian_points","9999"); assertEquals("conflict",upload(row).path("status").asString());
        assertEquals(1840L,jdbc.queryForObject("SELECT bailian_points FROM ranking_snapshot",Long.class)); assertEquals(1,count());
    }
    @Test void newCaptureIdSameObservationDeduplicates() throws Exception {
        var row=row(); var original=(String)row.get("capture_id"); upload(row); row.put("capture_id",UUID.randomUUID().toString());
        var retry=upload(row); assertEquals("duplicate",retry.path("status").asString());
        assertEquals(original,retry.path("stored_capture_id").asString()); assertEquals(1,count());
    }
    @Test void imageAliasDoesNotChangeObservationIdentity() throws Exception {
        var row=row(); upload(row); row.put("image_keys",List.of("renamed"));
        var b=batch(List.of(row)); b.put("images",List.of(Map.of("key","renamed","sha256",ImageStorage.hash(image))));
        var response=send(b,Map.of("renamed",image),true);
        assertEquals("duplicate",JSON.readTree(response.body()).path("results").get(0).path("status").asString());
    }
    @Test void changedImageContentIsAConflict() throws Exception {
        var row=row(); upload(row);
        var pixels=new BufferedImage(21,10,BufferedImage.TYPE_INT_RGB); var out=new ByteArrayOutputStream(); ImageIO.write(pixels,"png",out); image=out.toByteArray();
        assertEquals("conflict",upload(row).path("status").asString()); assertEquals(1,count());
    }
    @Test void missingIdAndUnknownGradeStayInvalid() throws Exception {
        var missing=row(); missing.remove("player_id"); var badGrade=row(); badGrade.put("grade",11);
        var response=send(batch(List.of(missing,badGrade)),Map.of("board",image),true);
        assertEquals(200,response.statusCode());
        for(var result:JSON.readTree(response.body()).path("results")) assertEquals("invalid",result.path("status").asString());
        assertEquals(0,count());
    }
    @Test void numericTypesAndOverflowAreRejected() throws Exception {
        for(Object value:List.of(1840,"9223372036854775808","-1","01840")) {
            var row=row(); row.put("bailian_points",value); assertEquals("invalid",upload(row).path("status").asString());
        }
        assertEquals(0,count());
    }
    @Test void timestampMustBeRealUtcMilliseconds() throws Exception {
        for(String value:List.of("2026-10-13T12:00:00Z","2026-10-13T20:00:00.123+08:00","2026-02-30T12:00:00.123Z","2026-10-13T12:00:00.123456Z")) {
            var row=row(); row.put("captured_at",value); assertEquals("invalid",upload(row).path("status").asString(),value);
        }
    }
    @Test void authenticatedUploadsAndFixedScopeRequired() throws Exception {
        var body=batch(List.of(row())); assertEquals(401,send(body,Map.of("board",image),false).statusCode());
        body.put("scope_key","another-server"); assertEquals(400,send(body,Map.of("board",image),true).statusCode()); assertEquals(0,count());
    }
    @Test void badImageHashOrMissingImageRejectsWholeBatch() throws Exception {
        var body=batch(List.of(row())); assertEquals(400,send(body,Map.of(),true).statusCode());
        body.put("images",List.of(Map.of("key","board","sha256","0".repeat(64))));
        assertEquals(400,send(body,Map.of("board",image),true).statusCode()); assertEquals(0,count());
    }
    @Test void disguisedNonImageIsRejected() throws Exception {
        image="not an image".getBytes(StandardCharsets.UTF_8);
        assertEquals(400,send(batch(List.of(row())),Map.of("board",image),true).statusCode()); assertEquals(0,count());
    }
    @Test void partialBatchReportsEveryRecord() throws Exception {
        var valid=row(); var invalid=row(); invalid.put("shikigami_id","4294967295");
        var response=send(batch(List.of(valid,invalid)),Map.of("board",image),true);
        var results=JSON.readTree(response.body()).path("results");
        assertEquals("saved",results.get(0).path("status").asString()); assertEquals("invalid",results.get(1).path("status").asString()); assertEquals(1,count());
    }
    @Test void concurrentRetriesStoreOneObservation() throws Exception {
        var row=row(); var pool=Executors.newFixedThreadPool(4);
        try {
            List<Callable<JsonNode>> tasks=new ArrayList<>(); for(int i=0;i<8;i++)tasks.add(() -> upload(row));
            var results=pool.invokeAll(tasks); int saved=0;
            for(var future:results) { String status=future.get().path("status").asString(); assertTrue(Set.of("saved","duplicate").contains(status)); if(status.equals("saved"))saved++; }
            assertEquals(1,saved); assertEquals(1,count());
        } finally { pool.shutdownNow(); }
    }
    @Test void databaseFailureRollsBackAndRetryWorks() throws Exception {
        jdbc.execute("CREATE TRIGGER fail_snapshot AFTER INSERT ON ranking_snapshot FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test rollback'");
        var row=row(); assertEquals(503,send(batch(List.of(row)),Map.of("board",image),true).statusCode()); assertEquals(0,count());
        jdbc.execute("DROP TRIGGER fail_snapshot"); assertEquals("saved",upload(row).path("status").asString());
    }
    @Test void conflictingCaptureAndObservationPointingToDifferentRowsNeverMerge() throws Exception {
        var first=row(); upload(first);
        var second=row(); second.put("player_id","another-player"); upload(second);
        var crossed=new LinkedHashMap<>(first); crossed.put("player_id","another-player");
        assertEquals("conflict",upload(crossed).path("status").asString()); assertEquals(2,count());
    }
    @Test void concurrentReRecognitionWithDifferentIdsUsesObservationUniqueKey() throws Exception {
        var pool=Executors.newFixedThreadPool(4);
        try {
            List<Callable<JsonNode>> tasks=new ArrayList<>();
            for(int i=0;i<4;i++) { var row=row(); tasks.add(() -> upload(row)); }
            int saved=0;
            for(var future:pool.invokeAll(tasks)) {
                var status=future.get().path("status").asString();
                assertTrue(Set.of("saved","duplicate").contains(status)); if(status.equals("saved"))saved++;
            }
            assertEquals(1,saved); assertEquals(1,count());
        } finally { pool.shutdownNow(); }
    }
    @Test void generatedWinRateAndLargeCountersAreExact() {
        assertNull(jdbc.queryForObject("SELECT win_rate FROM shikigami WHERE id=1",String.class));
        assertEquals("0",jdbc.queryForObject("SELECT CAST(sample_games AS CHAR) FROM shikigami WHERE id=1",String.class));
        jdbc.update("UPDATE shikigami SET sample_wins=1,sample_losses=2 WHERE id=1");
        assertEquals("3",jdbc.queryForObject("SELECT CAST(sample_games AS CHAR) FROM shikigami WHERE id=1",String.class));
        assertEquals("0.333333",jdbc.queryForObject("SELECT CAST(win_rate AS CHAR) FROM shikigami WHERE id=1",String.class));
        jdbc.update("UPDATE shikigami SET sample_wins=?,sample_losses=? WHERE id=1",Long.MAX_VALUE,Long.MAX_VALUE);
        assertEquals("18446744073709551614",jdbc.queryForObject("SELECT CAST(sample_games AS CHAR) FROM shikigami WHERE id=1",String.class));
        assertEquals("0.500000",jdbc.queryForObject("SELECT CAST(win_rate AS CHAR) FROM shikigami WHERE id=1",String.class));
        assertThrows(Exception.class,() -> jdbc.update("UPDATE shikigami SET sample_wins=9223372036854775808 WHERE id=1"));
    }
    @Test void identifiersAreCaseSensitiveAndForeignKeyPreventsOrphans() throws Exception {
        var a=row(); a.put("player_id","AbC"); upload(a); var b=row(); b.put("player_id","abc"); upload(b); assertEquals(2,count());
        assertThrows(Exception.class,() -> jdbc.update("DELETE FROM shikigami WHERE id=1"));
        assertThrows(Exception.class,() -> jdbc.update("UPDATE ranking_snapshot SET grade=11"));
    }
    @Test void schemaHasOnlyRequiredBusinessColumns() {
        assertEquals(9,jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='shikigami'",Integer.class));
        assertEquals(10,jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='ranking_snapshot'",Integer.class));
        assertEquals("+00:00",jdbc.queryForObject("SELECT @@session.time_zone",String.class));
    }

    Map<String,Object> observation(String time,String points,String wins) {
        var result=row(); result.put("captured_at","2026-10-13T"+time+".123Z");
        result.put("bailian_points",points); result.put("cumulative_wins",wins); return result;
    }
    @Test void uploadRebuildsWeightedStatisticsAndRetryIsIdempotent() throws Exception {
        var first=observation("12:00:00","2000","10"); var second=observation("13:00:00","2012","12");
        upload(first); upload(second); upload(second);
        assertEquals("3",jdbc.queryForObject("SELECT CAST(sample_games AS CHAR) FROM shikigami WHERE id=1",String.class));
        assertEquals(2L,jdbc.queryForObject("SELECT sample_wins FROM shikigami WHERE id=1",Long.class));
        assertEquals(1L,jdbc.queryForObject("SELECT sample_losses FROM shikigami WHERE id=1",Long.class));
        var result=statistics.statistics(1); assertEquals("0.666667",result.get("win_rate")); assertEquals("1",result.get("contributing_players"));
        assertEquals("2026-10-13T12:00:00.123Z",result.get("period_start"));
        assertEquals("2026-10-13T13:00:00.123Z",result.get("period_end"));
        assertEquals("0.666667",jdbc.queryForObject("SELECT CAST(win_rate AS CHAR) FROM shikigami WHERE id=1",String.class));
    }
    @Test void lateInvalidMiddleObservationReplacesPreviouslyValidInterval() throws Exception {
        upload(observation("12:00:00","2000","10")); upload(observation("14:00:00","2018","12"));
        assertEquals("2",statistics.statistics(1).get("sample_wins"));
        upload(observation("13:00:00","2010","11"));
        var result=statistics.statistics(1); assertEquals("0",result.get("sample_wins")); assertNull(result.get("win_rate"));
        assertEquals("0",jdbc.queryForObject("SELECT CAST(sample_games AS CHAR) FROM shikigami WHERE id=1",String.class));
        assertNull(jdbc.queryForObject("SELECT period_start FROM shikigami WHERE id=1",LocalDateTime.class));
        // Model the later admin correction and deletion paths without opening an unauthenticated admin API.
        jdbc.update("UPDATE ranking_snapshot SET bailian_points=2009 WHERE cumulative_wins=11");
        assertEquals("2",statistics.statistics(1).get("sample_wins"));
        jdbc.update("DELETE FROM ranking_snapshot WHERE cumulative_wins=11");
        assertEquals("2",statistics.statistics(1).get("sample_wins"));
        jdbc.update("UPDATE shikigami SET sample_wins=999,sample_losses=1 WHERE id=1");
        assertEquals("2",statistics.rankings().stream().filter(r -> r.get("id").equals("1")).findFirst().orElseThrow().get("sample_wins"));
    }
    @Test void failedSummaryUpdateRollsBackSnapshotToo() throws Exception {
        jdbc.execute("CREATE TRIGGER fail_statistics BEFORE UPDATE ON shikigami FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test summary rollback'");
        var row=row();
        try { assertEquals(503,send(batch(List.of(row)),Map.of("board",image),true).statusCode()); assertEquals(0,count()); }
        finally { jdbc.execute("DROP TRIGGER fail_statistics"); }
        assertEquals("saved",upload(row).path("status").asString());
    }
    @Test void concurrentDifferentObservationsProduceOneConsistentSummary() throws Exception {
        var pool=Executors.newFixedThreadPool(3);
        try {
            var rows=List.of(observation("12:00:00","2000","10"),observation("13:00:00","2009","11"),observation("14:00:00","2012","12"));
            List<Callable<JsonNode>> tasks=rows.stream().<Callable<JsonNode>>map(r -> () -> upload(r)).toList();
            for(var future:pool.invokeAll(tasks)) assertEquals("saved",future.get().path("status").asString());
            assertEquals(3,count()); assertEquals(2L,jdbc.queryForObject("SELECT sample_wins FROM shikigami WHERE id=1",Long.class));
            assertEquals(1L,jdbc.queryForObject("SELECT sample_losses FROM shikigami WHERE id=1",Long.class));
        } finally { pool.shutdownNow(); }
    }
    @Test void publicStatisticsAreAnonymousAndDoNotLeakPlayerIdsOrImages() throws Exception {
        upload(observation("12:00:00","2000","10")); upload(observation("13:00:00","2009","11"));
        for(String path:List.of("/api/rankings","/api/shikigami","/api/shikigami/1/statistics")) {
            var response=CLIENT.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path)).GET().build(),HttpResponse.BodyHandlers.ofString());
            assertEquals(200,response.statusCode(),response.body()); assertFalse(response.body().contains("000123"));
            assertFalse(response.body().contains("source_image_ref")); assertTrue(response.body().contains("synthetic-test-v1"));
        }
        var missing=CLIENT.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/shikigami/999/statistics")).GET().build(),HttpResponse.BodyHandlers.ofString());
        assertEquals(404,missing.statusCode());
    }
    @Test void expiredWindowDropsOldTotalsEvenWithoutNewUploads() throws Exception {
        upload(observation("12:00:00","2000","10")); upload(observation("13:00:00","2009","11"));
        jdbc.update("UPDATE ranking_snapshot SET captured_at=DATE_SUB(captured_at, INTERVAL 8 DAY)");
        var result=statistics.statistics(1); assertEquals("NO_SAMPLES",result.get("status")); assertNull(result.get("win_rate"));
        assertEquals("0",jdbc.queryForObject("SELECT CAST(sample_games AS CHAR) FROM shikigami WHERE id=1",String.class));
        assertEquals(0L,jdbc.queryForObject("SELECT sample_wins FROM shikigami WHERE id=1",Long.class));
    }
    @Test void gradeStatisticsPreserveTransitionsAndReturnCountsAsStrings() throws Exception {
        var a=observation("12:00:00","2000","1000");
        var b=observation("13:00:00","2003","1001");
        var c=observation("14:00:00","2012","1002"); c.put("grade",6);
        var d=observation("15:00:00","2006","1002"); d.put("grade",6);
        upload(a); assertEquals("0",statistics.statistics(1).get("sample_wins"));
        upload(b); upload(c); upload(d);
        var response=CLIENT.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/shikigami/1/statistics")).GET().build(),HttpResponse.BodyHandlers.ofString());
        assertEquals(200,response.statusCode()); var json=JSON.readTree(response.body()); var grades=json.path("grade_statistics");
        assertEquals(6,grades.size()); assertEquals(5,grades.get(0).path("grade").asInt());
        assertEquals("1",grades.get(0).path("sample_wins").asString()); assertEquals("0.500000",grades.get(0).path("win_rate").asString());
        assertEquals("1",grades.get(1).path("sample_losses").asString()); assertEquals("0.000000",grades.get(1).path("win_rate").asString());
        assertEquals("1",json.path("unassigned_grade").path("sample_wins").asString());
        assertEquals("2",json.path("sample_wins").asString()); assertEquals("2",json.path("sample_losses").asString());
        assertFalse(response.body().contains("000123"));
        // A corrected middle grade must rebuild the timeline, not leave stale grade aggregates.
        jdbc.update("UPDATE ranking_snapshot SET grade=5 WHERE bailian_points=2012");
        var corrected=JSON.valueToTree(statistics.statistics(1));
        assertEquals("2",corrected.path("sample_wins").asString());
        assertEquals("2",corrected.path("grade_statistics").get(0).path("sample_wins").asString());
        assertEquals("NO_SAMPLES",corrected.path("grade_statistics").get(1).path("status").asString());
        assertEquals("1",corrected.path("unassigned_grade").path("sample_losses").asString());
    }

    @Test void coverageDistinguishesBaselineAndUsesLatestPlayerGradeWithinSeasonAndWindow() throws Exception {
        var first=observation("12:00:00","2000","10"); upload(first);
        var baseline=JSON.valueToTree(statistics.statistics(1));
        assertEquals("1",baseline.path("observation_count").asString());
        assertEquals("1",baseline.path("observed_players").asString());
        assertEquals("0",baseline.path("sample_games").asString());
        var next=observation("13:00:00","2009","11"); next.put("grade",6); upload(next);
        var other=observation("14:00:00","2000","10"); other.put("season_key","OTHER"); upload(other);
        var result=JSON.valueToTree(statistics.statistics(1));
        assertEquals("2",result.path("observation_count").asString());
        assertEquals("1",result.path("observed_players").asString());
        assertEquals("2026-10-13T13:00:00.123Z",result.path("latest_capture_at").asString());
        assertEquals("0",result.path("latest_observed_grades").get(0).path("player_count").asString());
        assertEquals("1",result.path("latest_observed_grades").get(1).path("player_count").asString());
        jdbc.update("UPDATE ranking_snapshot SET captured_at=DATE_SUB(captured_at, INTERVAL 8 DAY)");
        var expired=JSON.valueToTree(statistics.statistics(1));
        assertEquals("0",expired.path("observation_count").asString());
        assertTrue(expired.path("latest_capture_at").isNull());
    }
}
