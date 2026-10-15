package cn.baiwen.aide.ingestion;

import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import javax.imageio.ImageIO;
import javax.imageio.stream.MemoryCacheImageInputStream;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import cn.baiwen.aide.common.*;

@Component
public class ImageStorage {
    private final Path root;
    public ImageStorage(AppProperties properties) { root=properties.storageRoot().toAbsolutePath().normalize(); }
    public record CheckedImage(String sha256, byte[] bytes) {}

    public static String hash(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    public CheckedImage check(MultipartFile file, String sha) throws IOException {
        if (file==null || file.isEmpty() || file.getSize()>8L*1024*1024) throw ApiException.invalid("图片缺失或超过 8 MiB");
        byte[] bytes=file.getBytes();
        if (!hash(bytes).equals(sha)) throw ApiException.invalid("图片 SHA-256 与 manifest 不符");
        try (var input=new MemoryCacheImageInputStream(new ByteArrayInputStream(bytes))) {
            var readers=ImageIO.getImageReaders(input);
            if (!readers.hasNext()) throw ApiException.invalid("文件不是有效 PNG/JPEG 图片");
            var reader=readers.next();
            try {
                reader.setInput(input);
                String format=reader.getFormatName();
                if (!Set.of("png","jpeg").contains(format.toLowerCase(Locale.ROOT))) throw ApiException.invalid("只接收 PNG/JPEG 图片");
                int width=reader.getWidth(0), height=reader.getHeight(0);
                if (width<1 || height<1 || (long)width*height>20_000_000L) throw ApiException.invalid("图片尺寸超过限制");
                if (reader.read(0)==null) throw ApiException.invalid("图片解码失败");
            } finally { reader.dispose(); }
        } catch (javax.imageio.IIOException e) { throw ApiException.invalid("图片损坏，无法解码"); }
        return new CheckedImage(sha,bytes);
    }
    public String persist(List<CheckedImage> images) throws IOException {
        // Canonicalize by contents, not client filenames or multipart aliases.
        var hashes=new TreeSet<String>();
        for (var image:images) {
            save("images/"+image.sha256().substring(0,2)+"/"+image.sha256()+".image",image.bytes());
            hashes.add(image.sha256());
        }
        String json="{\"sha256\":["+String.join(",",hashes.stream().map(s -> "\""+s+"\"").toList())+"]}\n";
        byte[] manifest=json.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        String ref="manifests/"+hash(manifest)+".json";
        save(ref,manifest);
        return ref;
    }
    private synchronized void save(String relative, byte[] bytes) throws IOException {
        Path destination=root.resolve(relative);
        Files.createDirectories(destination.getParent());
        if (Files.exists(destination)) {
            if (!hash(Files.readAllBytes(destination)).equals(hash(bytes))) throw new IOException("已存图片内容校验失败");
            return;
        }
        Path temporary=Files.createTempFile(destination.getParent(),"incoming-",".tmp");
        try {
            Files.write(temporary,bytes);
            try {
                try { Files.move(temporary,destination,StandardCopyOption.ATOMIC_MOVE); }
                catch (AtomicMoveNotSupportedException e) { Files.move(temporary,destination); }
            } catch (IOException e) {
                // A competing process may publish first. Windows can report AccessDenied,
                // not FileAlreadyExists. Accept only a complete, byte-identical destination.
                if (!Files.isRegularFile(destination) || !hash(Files.readAllBytes(destination)).equals(hash(bytes))) throw e;
            }
        } finally { Files.deleteIfExists(temporary); }
    }
}
