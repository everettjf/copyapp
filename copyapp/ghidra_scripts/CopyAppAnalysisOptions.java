// Copy APP's direct Ghidra analysis profile for a single named analyzer.
// Uses Ghidra's headless script API; behavior was informed by REA's MIT-licensed
// analyzer-option bridge, without copying that bridge into this project.
import ghidra.app.util.headless.HeadlessScript;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class CopyAppAnalysisOptions extends HeadlessScript {
    @Override
    public void run() throws Exception {
        String[] arguments = getScriptArgs();
        if (arguments.length != 2 || arguments[0].isBlank()) {
            throw new IllegalArgumentException("expected analyzer name and output directory");
        }
        String name = arguments[0];
        Map<String, String> before = getCurrentAnalysisOptionsAndValues(currentProgram);
        if (!before.containsKey(name)) {
            throw new IllegalArgumentException("unknown Ghidra analyzer: " + name);
        }
        setAnalysisOption(currentProgram, name, "false");
        Map<String, String> after = getCurrentAnalysisOptionsAndValues(currentProgram);
        if (!"false".equals(after.get(name))) {
            throw new IllegalStateException("analyzer stayed enabled: " + name);
        }
        Files.writeString(Path.of(arguments[1]).resolve("analysis-options.txt"),
                          name + "=false\n", StandardCharsets.UTF_8);
        println("COPYAPP_ANALYZER_DISABLED " + name);
    }
}
