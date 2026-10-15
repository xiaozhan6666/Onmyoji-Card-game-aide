package cn.baiwen.aide.ingestion;

import cn.baiwen.aide.common.AppProperties;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class ImageStorageTest {
    @TempDir Path directory;
    ImageStorage storage() { return new ImageStorage(new AppProperties("test","a".repeat(40),directory)); }
    @Test void simultaneousFirstWritesFromDifferentInstancesPublishCompleteFiles() throws Exception {
        var pool=Executors.newFixedThreadPool(8);
        try {
            for(int round=0;round<12;round++) {
                byte[] bytes=new byte[65536]; new Random(round).nextBytes(bytes);
                String hash=ImageStorage.hash(bytes); var barrier=new CyclicBarrier(8);
                List<Callable<String>> tasks=new ArrayList<>();
                for(int worker=0;worker<8;worker++) tasks.add(() -> {
                    var store=storage(); barrier.await(10,TimeUnit.SECONDS);
                    return store.persist(List.of(new ImageStorage.CheckedImage(hash,bytes)));
                });
                Set<String> manifests=new HashSet<>();
                for(var result:pool.invokeAll(tasks)) manifests.add(result.get());
                assertEquals(1,manifests.size()); assertTrue(Files.readString(directory.resolve(manifests.iterator().next())).contains(hash));
                assertArrayEquals(bytes,Files.readAllBytes(directory.resolve("images/"+hash.substring(0,2)+"/"+hash+".image")));
            }
            try(var paths=Files.walk(directory)) { assertFalse(paths.anyMatch(p -> p.toString().endsWith(".tmp"))); }
        } finally { pool.shutdownNow(); }
    }
    @Test void existingCorruptContentIsNotTreatedAsASuccessfulRetry() throws Exception {
        byte[] bytes={1,2,3}; String hash=ImageStorage.hash(bytes);
        Path path=directory.resolve("images/"+hash.substring(0,2)+"/"+hash+".image");
        Files.createDirectories(path.getParent()); Files.write(path,new byte[]{9});
        assertThrows(java.io.IOException.class,() -> storage().persist(List.of(new ImageStorage.CheckedImage(hash,bytes))));
    }
}
