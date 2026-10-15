package cn.baiwen.aide.statistics;

import cn.baiwen.aide.ingestion.Snapshot;
import java.io.*;
import java.math.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import static org.junit.jupiter.api.Assertions.*;
import static cn.baiwen.aide.statistics.IntervalCalculator.Reason.*;

class StatisticsTest {
    ScoreRules rules;
    final Instant start=Instant.parse("2026-10-13T00:00:00Z"), end=start.plus(Duration.ofDays(1));
    final StatisticsProperties settings=new StatisticsProperties("test","test-season",Duration.ofDays(7),Duration.ofHours(24),1);
    @BeforeEach void setup() throws Exception { rules=ScoreRules.read(getClass().getResourceAsStream("/rules-test.yaml")); }
    Snapshot row(long id, long points, long wins, int grade) {
        var row=new Snapshot(); row.id=id; row.shikigamiId=1L; row.playerId="0001"; row.seasonKey="test-season";
        row.bailianPoints=points; row.cumulativeWins=wins; row.grade=grade;
        row.capturedAt=LocalDateTime.ofInstant(start.plusSeconds(id*60),ZoneOffset.UTC); return row;
    }
    IntervalCalculator.Result calculate(Snapshot a, Snapshot b) { return IntervalCalculator.calculate(a,b,rules,"integration-test",Duration.ofDays(1)); }
    StatisticsEngine.Report summarize(Snapshot... rows) { return StatisticsEngine.summarize(List.of(rows),rules,"integration-test",settings,start,end); }

    @ParameterizedTest @CsvSource({"5,6,9,6","7,8,13,7","9,9,16,9","10,10,19,10"})
    void fourGroupsAndSameGroupPromotions(int beforeGrade,int afterGrade,int win,int loss) {
        var result=calculate(row(1,2000,10,beforeGrade),row(2,2000+win*4-loss*3,14,afterGrade));
        assertEquals(INFERRED,result.reason()); assertEquals(4,result.wins()); assertEquals(3,result.losses());
    }
    @Test void groupChangeAndUnknownGrade() {
        assertEquals(SCORING_GROUP_CHANGED,calculate(row(1,2000,10,6),row(2,2013,11,7)).reason());
        assertEquals(UNKNOWN_GRADE,calculate(row(1,2000,10,4),row(2,2009,11,4)).reason());
    }
    @Test void noChangeAllLossAndAllWin() {
        assertEquals(NO_CHANGE,calculate(row(1,2000,10,5),row(2,2000,10,5)).reason());
        var losses=calculate(row(1,2000,10,5),row(2,1982,10,5)); assertEquals(3,losses.losses()); assertEquals(0,losses.wins());
        var wins=calculate(row(1,2000,10,5),row(2,2018,12,5)); assertEquals(2,wins.wins()); assertEquals(0,wins.losses());
    }
    @Test void decreasingWinsNegativeAndFractionalLosses() {
        assertEquals(WINS_DECREASED,calculate(row(1,2000,10,5),row(2,2000,9,5)).reason());
        assertEquals(NEGATIVE_LOSSES,calculate(row(1,2000,10,5),row(2,2010,11,5)).reason());
        assertEquals(NON_INTEGER_LOSSES,calculate(row(1,2000,10,5),row(2,2008,11,5)).reason());
    }
    @Test void identitySeasonAndTimeAreBoundaries() {
        var a=row(1,2000,10,5); var b=row(2,2009,11,5); b.playerId="different";
        assertEquals(DIFFERENT_IDENTITY,calculate(a,b).reason()); b.playerId=a.playerId; b.seasonKey="next";
        assertEquals(CROSS_SEASON,calculate(a,b).reason()); b.seasonKey=a.seasonKey; b.capturedAt=a.capturedAt;
        assertEquals(INVALID_TIME,calculate(a,b).reason()); b.capturedAt=a.capturedAt.plusDays(1).plusSeconds(1);
        assertEquals(INTERVAL_TOO_LONG,calculate(a,b).reason());
    }
    @Test void unconfirmedRulesCannotPublish() throws Exception {
        String yaml=new String(getClass().getResourceAsStream("/rules-test.yaml").readAllBytes(),StandardCharsets.UTF_8);
        rules=ScoreRules.read(new ByteArrayInputStream(yaml.replace("conditions_confirmed: true","conditions_confirmed: false").getBytes(StandardCharsets.UTF_8)));
        assertEquals(RULES_UNCONFIRMED,calculate(row(1,2000,10,5),row(2,2009,11,5)).reason());
        assertEquals("RULES_UNCONFIRMED",summarize(row(1,2000,10,5),row(2,2009,11,5)).status());
    }
    @Test void rulePeriodThresholdAndScopeAreChecked() {
        var a=row(1,2000,10,5); var b=row(2,2009,11,5);
        a.capturedAt=LocalDateTime.parse("2026-09-30T23:59:00"); b.capturedAt=a.capturedAt.plusMinutes(2);
        assertEquals(OUTSIDE_RULE_PERIOD,calculate(a,b).reason());
        a.capturedAt=LocalDateTime.parse("2026-10-31T23:59:00"); b.capturedAt=a.capturedAt.plusMinutes(1);
        assertEquals(OUTSIDE_RULE_PERIOD,calculate(a,b).reason());
        rules=new ScoreRules(rules.version(),rules.source(),rules.sha256(),rules.scopeKey(),rules.seasons(),true,1000L,rules.from(),rules.to(),rules.grades(),rules.calculationMode());
        assertEquals(BELOW_RULE_MINIMUM,calculate(row(1,999,0,5),row(2,1008,1,5)).reason());
        assertEquals(RULES_UNCONFIRMED,IntervalCalculator.calculate(row(1,2000,0,5),row(2,2009,1,5),rules,"wrong",Duration.ofDays(1)).reason());
    }
    @Test void largeIntermediateMultiplicationDoesNotOverflow() {
        var result=calculate(row(1,0,0,5),row(2,9_000_000_000_000_000_000L,3_000_000_000_000_000_000L,5));
        assertEquals(INFERRED,result.reason()); assertEquals(3_000_000_000_000_000_000L,result.losses());
        assertEquals(COUNTER_OVERFLOW,calculate(row(1,0,0,5),row(2,0,Long.MAX_VALUE-1,5)).reason());
    }
    @ParameterizedTest @CsvSource({"0,0,0","999,999,999","1000,1000,1000","1001,1000.4,1000","1004,1001.6,1001","3000,1800,1800","3001,1800.2,1800","3004,1800.8,1800","3200,1840,1840"})
    void seasonalResetIsFlooredAfterExactCalculation(long input,String expected,long rounded) {
        var result=SeasonResetCalculator.reset(input);
        assertEquals(0,new BigDecimal(expected).compareTo(result.exactPoints())); assertEquals(rounded,result.resetPoints());
    }
    @Test void resetRejectsNegativeAndHandlesMaximum() {
        assertThrows(IllegalArgumentException.class,() -> SeasonResetCalculator.reset(-1));
        assertEquals(0,new BigDecimal("1844674407370956361.4").compareTo(SeasonResetCalculator.reset(Long.MAX_VALUE).exactPoints()));
        assertEquals(1_844_674_407_370_956_361L,SeasonResetCalculator.reset(Long.MAX_VALUE).resetPoints());
    }
    @Test void sortingAdjacencyAndWeightedRate() {
        var a=row(1,2000,10,5); var b=row(2,2009,11,5); var c=row(3,2012,12,5);
        var d=row(4,2000,10,5); d.playerId="0002"; var e=row(5,1982,10,5); e.playerId=d.playerId;
        var report=summarize(c,e,a,d,b);
        assertEquals(2,report.wins()); assertEquals(4,report.losses()); assertEquals(2,report.players());
        assertEquals(new BigDecimal("0.333333"),report.winRate()); assertEquals(3,report.intervals().size());
        assertEquals(a.capturedAt,report.periodStart()); assertEquals(e.capturedAt,report.periodEnd());
    }
    @Test void invalidMiddleObservationNeverGetsBridged() {
        var report=summarize(row(1,2000,10,5),row(2,2010,11,5),row(3,2018,12,5));
        assertEquals(0,report.wins()); assertEquals(2,report.intervals().size()); assertEquals("NO_SAMPLES",report.status());
        assertEquals(1L,report.exclusions().get(NEGATIVE_LOSSES)); assertEquals(1L,report.exclusions().get(NON_INTEGER_LOSSES));
    }
    @Test void onlyCompleteWindowIntervalsAndNoFutureRows() {
        var a=row(1,2000,10,5); a.capturedAt=LocalDateTime.ofInstant(start.minusMillis(1),ZoneOffset.UTC);
        var b=row(2,2009,11,5); b.capturedAt=LocalDateTime.ofInstant(start,ZoneOffset.UTC);
        var c=row(3,2018,12,5); c.capturedAt=LocalDateTime.ofInstant(end,ZoneOffset.UTC);
        var d=row(4,2027,13,5); d.capturedAt=LocalDateTime.ofInstant(end.plusMillis(1),ZoneOffset.UTC);
        var report=summarize(a,b,c,d); assertEquals(1,report.wins()); assertEquals(1,report.intervals().size());
        assertEquals(b.capturedAt,report.periodStart()); assertEquals(c.capturedAt,report.periodEnd());
    }
    @Test void seasonBoundaryIsABarrierEvenWhenOtherSeasonHasValidArithmetic() {
        var a=row(1,2000,10,5); var b=row(2,2009,11,5); b.seasonKey="other"; var c=row(3,2018,12,5);
        var report=summarize(a,b,c); assertEquals(0,report.wins()); assertEquals(2L,report.exclusions().get(CROSS_SEASON));
    }
    @Test void minimumGamesMasksRateButKeepsEvidence() {
        var minimum=new StatisticsProperties("test","test-season",Duration.ofDays(7),Duration.ofDays(1),10);
        var report=StatisticsEngine.summarize(List.of(row(1,2000,10,5),row(2,2009,11,5)),rules,"integration-test",minimum,start,end);
        assertEquals("INSUFFICIENT_SAMPLES",report.status()); assertNull(report.winRate()); assertEquals(1,report.wins());
    }
    @Test void aggregateOverflowDoesNotWrapOrPublishPartialTotals() {
        var a=row(1,0,0,5); var b=row(2,0,6_000_000_000_000_000_000L,5);
        var c=row(3,0,0,5); c.playerId="b"; var d=row(4,0,6_000_000_000_000_000_000L,5); d.playerId="b";
        var report=summarize(a,b,c,d); assertEquals("COUNTER_OVERFLOW",report.status()); assertNull(report.winRate()); assertEquals(0,report.wins());
    }
    @Test void malformedRuleFilesFailClosed() throws Exception {
        String yaml=new String(getClass().getResourceAsStream("/rules-test.yaml").readAllBytes(),StandardCharsets.UTF_8);
        for(String invalid:List.of(yaml+"\nversion: duplicate\n",yaml.replace("loss_points: -6","loss_points: 6"),
                yaml.replace("grades: [7, 8]","grades: [5, 8]"),yaml.replace("scope_key: integration-test","scope_key: null"),
                yaml.replace("win_points: 9","win_points: 9.5"),yaml+"\nunknown: true\n",yaml+"\ncalculation_mode: typo\n",
                yaml.replace("effective_from: '2026-10-01T00:00:00Z'","effective_from: null").replace("conditions_confirmed: true","conditions_confirmed: false")+"\ncalculation_mode: observation\n")) {
            assertThrows(RuntimeException.class,() -> ScoreRules.read(new ByteArrayInputStream(invalid.getBytes(StandardCharsets.UTF_8))));
        }
    }
    @Test void s56ObservationUsesOnlyNewIntervalsWithoutPretendingConditionsAreConfirmed() throws Exception {
        var current=ScoreRules.read(getClass().getResourceAsStream("/rules/score-rules.yaml"));
        assertEquals("observation",current.calculationMode()); assertFalse(current.conditionsConfirmed());
        assertTrue(current.ready("local-development","S56")); assertFalse(current.ready("local-development","S55"));
        assertFalse(current.ready("other-scope","S56"));
        var a=row(1,2000,9000,5); var b=row(2,2009,9001,5); a.seasonKey="S56"; b.seasonKey="S56";
        a.capturedAt=LocalDateTime.ofInstant(current.from(),ZoneOffset.UTC); b.capturedAt=a.capturedAt.plusMinutes(1);
        assertEquals(INFERRED,IntervalCalculator.calculate(a,b,current,"local-development",Duration.ofDays(1)).reason());
        a.capturedAt=a.capturedAt.minusSeconds(1);
        assertEquals(OUTSIDE_RULE_PERIOD,IntervalCalculator.calculate(a,b,current,"local-development",Duration.ofDays(1)).reason());
    }
    @Test void firstObservationWithLifetimeWinsOnlyEstablishesBaseline() {
        var a=row(1,2000,9000,5); assertEquals(0,summarize(a).wins());
        var b=row(2,2003,9001,5); var report=summarize(a,b);
        assertEquals(1,report.wins()); assertEquals(1,report.losses());
        assertEquals(new BigDecimal("0.500000"),report.grades().getFirst().winRate());
    }
    @Test void rankTransitionCannotBeAssignedToEitherEndpointOrBridged() {
        var a=row(1,2000,10,5); var b=row(2,2009,11,6); var c=row(3,2003,11,6); var d=row(4,2012,12,5);
        var report=summarize(d,b,a,c);
        assertEquals(2,report.wins()); assertEquals(1,report.losses());
        assertEquals(0,report.grades().getFirst().wins()); assertEquals("NO_SAMPLES",report.grades().getFirst().status());
        assertEquals(0,report.grades().get(1).wins()); assertEquals(1,report.grades().get(1).losses());
        assertEquals(new BigDecimal("0.000000"),report.grades().get(1).winRate());
        assertEquals(2,report.unassignedGrade().wins()); assertEquals(2,report.unassignedGrade().intervalCount());
        assertEquals(5,report.intervals().getFirst().beforeGrade()); assertEquals(6,report.intervals().getFirst().afterGrade());
    }
    @Test void perGradeRateIsWeightedAndPlayerCanContributeToSeveralGrades() {
        var a=row(1,2000,0,5); var b=row(2,2030,4,5);
        var c=row(3,2039,5,6); var d=row(4,2033,5,6);
        var e=row(5,2000,0,5); e.playerId="second"; var f=row(6,1982,0,5); f.playerId=e.playerId;
        var report=summarize(a,b,c,d,e,f); var five=report.grades().getFirst();
        assertEquals(4,five.wins()); assertEquals(4,five.losses()); assertEquals(new BigDecimal("0.500000"),five.winRate());
        assertEquals(2,five.players()); assertEquals(1,report.grades().get(1).players()); assertEquals(2,report.players());
        assertEquals(report.wins(),report.grades().stream().mapToLong(StatisticsEngine.GradeReport::wins).sum()+report.unassignedGrade().wins());
        assertEquals(report.losses(),report.grades().stream().mapToLong(StatisticsEngine.GradeReport::losses).sum()+report.unassignedGrade().losses());
    }
    @Test void otherGradesAndMinimumSamplesApplySeparately() {
        var observations=new ArrayList<Snapshot>();
        for(int grade=5;grade<=10;grade++) {
            var a=row(grade*2,2000,100,grade); var b=row(grade*2+1,2000+rules.grades().get(grade).win(),101,grade);
            a.playerId="player-"+grade; b.playerId=a.playerId; observations.add(a); observations.add(b);
        }
        var minimum=new StatisticsProperties("test","test-season",Duration.ofDays(7),Duration.ofDays(1),2);
        var report=StatisticsEngine.summarize(observations,rules,"integration-test",minimum,start,end);
        assertEquals("INFERRED",report.status()); assertEquals(6,report.wins());
        for(var grade:report.grades()) { assertEquals(1,grade.wins()); assertEquals("INSUFFICIENT_SAMPLES",grade.status()); assertNull(grade.winRate()); }
    }
    @Test void cumulativeWinsPersistingThroughSeasonDoesNotMakeCrossSeasonDifferenceValid() {
        var a=row(1,3200,1000,10); a.seasonKey="prior-season";
        var b=row(2,1840,1000,5); var c=row(3,1849,1001,5);
        var report=summarize(a,b,c); assertEquals(1,report.wins()); assertEquals(0,report.losses());
        assertEquals(1L,report.exclusions().get(CROSS_SEASON)); assertEquals(b.capturedAt,report.periodStart());
    }
}
