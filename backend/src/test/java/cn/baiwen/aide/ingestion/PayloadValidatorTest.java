package cn.baiwen.aide.ingestion;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;
import cn.baiwen.aide.common.ApiException;
import static org.junit.jupiter.api.Assertions.*;

class PayloadValidatorTest {
    final JsonMapper json=JsonMapper.builder().build();
    @Test void rejectsNumbersInsteadOfDecimalStrings() {
        assertThrows(ApiException.class, () -> PayloadValidator.number(json.readTree("{\"value\":123}"),"value",Long.MAX_VALUE,0));
    }
    @Test void unsignedDatabaseRangeMustNotOverflowJava() {
        assertThrows(ApiException.class, () -> PayloadValidator.number(json.readTree("{\"value\":\"9223372036854775808\"}"),"value",Long.MAX_VALUE,0));
    }
    @Test void opaquePlayerIdPreservesZerosAndCase() {
        assertEquals("000AbC",PayloadValidator.identifier(json.readTree("{\"player_id\":\"000AbC\"}"),"player_id"));
    }
}
