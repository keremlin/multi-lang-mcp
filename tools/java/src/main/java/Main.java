import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;

public class Main {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("javaVersion", System.getProperty("java.version"));
        data.put("os", System.getProperty("os.name"));
        data.put("args", args);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("success", true);
        result.put("data", data);

        System.out.println(mapper.writeValueAsString(result));
    }
}
