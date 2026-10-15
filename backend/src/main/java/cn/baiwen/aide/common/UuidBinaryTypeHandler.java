package cn.baiwen.aide.common;

import java.nio.ByteBuffer;
import java.sql.*;
import java.util.UUID;
import org.apache.ibatis.type.*;

@MappedTypes(UUID.class)
@MappedJdbcTypes(value=JdbcType.BINARY, includeNullJdbcType=true)
public class UuidBinaryTypeHandler extends BaseTypeHandler<UUID> {
    @Override public void setNonNullParameter(PreparedStatement p, int i, UUID value, JdbcType type) throws SQLException {
        p.setBytes(i, ByteBuffer.allocate(16).putLong(value.getMostSignificantBits()).putLong(value.getLeastSignificantBits()).array());
    }
    private UUID decode(byte[] value) throws SQLException {
        if (value == null) return null;
        if (value.length != 16) throw new SQLException("UUID 字段长度错误");
        var b=ByteBuffer.wrap(value); return new UUID(b.getLong(), b.getLong());
    }
    @Override public UUID getNullableResult(ResultSet r, String column) throws SQLException { return decode(r.getBytes(column)); }
    @Override public UUID getNullableResult(ResultSet r, int column) throws SQLException { return decode(r.getBytes(column)); }
    @Override public UUID getNullableResult(CallableStatement s, int column) throws SQLException { return decode(s.getBytes(column)); }
}
