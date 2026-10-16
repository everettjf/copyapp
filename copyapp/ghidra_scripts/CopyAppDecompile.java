// Copy APP's bounded Ghidra headless post-script for one or more functions.
// The function relationship fields below adapt the dossier idea and the
// getCallingFunctions/getCalledFunctions and BasicBlockModel/reference
// observations from REA's
// bridge/ghidra/ReaGhidraBridge.java at 21eff3bae10f58711a35ad44f86e9f96f9bb4790.
// Copy APP changed the output to a bounded, one-shot JSON artifact and does
// not embed REA's session bridge. REA's MIT license is in REA-LICENSE.txt.
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.block.BasicBlockModel;
import ghidra.program.model.block.CodeBlock;
import ghidra.program.model.block.CodeBlockIterator;
import ghidra.program.model.block.CodeBlockReference;
import ghidra.program.model.block.CodeBlockReferenceIterator;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.Reference;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;

public class CopyAppDecompile extends GhidraScript {
    private static final int MAX_RELATED_FUNCTIONS = 256;
    private static final int MAX_BLOCKS = 256;
    private static final int MAX_REFERENCES = 256;
    private static final int MAX_INSTRUCTIONS = 20000;

    private static String hex(Address address) {
        return "0x" + address;
    }

    private JsonObject functionFacts(Function function) throws Exception {
        JsonObject facts = new JsonObject();
        facts.addProperty("schema_version", 2);
        facts.addProperty("address", hex(function.getEntryPoint()));
        facts.addProperty("name", function.getName());
        facts.addProperty("signature", function.getPrototypeString(false, true));
        facts.addProperty("is_thunk", function.isThunk());
        facts.addProperty("is_external", function.isExternal());
        addRelated(facts, "callers", function.getCallingFunctions(monitor));
        addRelated(facts, "callees", function.getCalledFunctions(monitor));
        addBlocks(facts, function);
        addInstructionReferences(facts, function);
        facts.addProperty("limitation", "Ghidra static observations; bounded instruction references and basic blocks omit unresolved indirect calls, data-origin references and runtime execution.");
        return facts;
    }

    private void addBlocks(JsonObject facts, Function function) throws Exception {
        BasicBlockModel model = new BasicBlockModel(currentProgram, false);
        CodeBlockIterator blocks = model.getCodeBlocksContaining(function.getBody(), monitor);
        JsonArray values = new JsonArray();
        boolean truncated = false;
        List<CodeBlock> retained = new ArrayList<>();
        while (blocks.hasNext()) {
            monitor.checkCancelled();
            if (retained.size() >= MAX_BLOCKS) {
                truncated = true;
                break;
            }
            retained.add(blocks.next());
        }
        retained.sort((left, right) -> left.getFirstStartAddress().compareTo(
            right.getFirstStartAddress()));
        for (CodeBlock block : retained) {
            JsonObject item = new JsonObject();
            item.addProperty("start", hex(block.getFirstStartAddress()));
            item.addProperty("end_inclusive", hex(block.getMaxAddress()));
            TreeMap<Address, Boolean> successors = new TreeMap<>();
            CodeBlockReferenceIterator destinations = block.getDestinations(monitor);
            while (destinations.hasNext()) {
                monitor.checkCancelled();
                CodeBlockReference destination = destinations.next();
                CodeBlock target = destination.getDestinationBlock();
                if (target != null && !destination.getFlowType().isCall() &&
                        function.getBody().contains(target.getFirstStartAddress())) {
                    successors.put(target.getFirstStartAddress(), true);
                }
            }
            JsonArray edges = new JsonArray();
            for (Address address : successors.keySet()) {
                edges.add(hex(address));
            }
            item.add("successors", edges);
            values.add(item);
        }
        facts.add("basic_blocks", values);
        facts.addProperty("basic_blocks_truncated", truncated);
    }

    private void addInstructionReferences(JsonObject facts, Function function) throws Exception {
        InstructionIterator instructions = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        TreeMap<String, JsonObject> observed = new TreeMap<>();
        int scanned = 0;
        boolean truncated = false;
        while (instructions.hasNext()) {
            monitor.checkCancelled();
            if (scanned++ >= MAX_INSTRUCTIONS) {
                truncated = true;
                break;
            }
            Instruction instruction = instructions.next();
            for (Reference reference : instruction.getReferencesFrom()) {
                monitor.checkCancelled();
                if (observed.size() >= MAX_REFERENCES) {
                    truncated = true;
                    break;
                }
                Address target = reference.getToAddress();
                if (!reference.getFromAddress().isMemoryAddress() ||
                        !target.isMemoryAddress()) {
                    continue;
                }
                JsonObject item = new JsonObject();
                item.addProperty("from", hex(reference.getFromAddress()));
                item.addProperty("to", hex(target));
                item.addProperty("type", reference.getReferenceType().getName());
                Data data = currentProgram.getListing().getDataContaining(target);
                Object value = data == null ? null : data.getValue();
                if (value instanceof String) {
                    String preview = (String) value;
                    item.addProperty("string_preview", preview.substring(0, Math.min(256, preview.length())));
                }
                String key = item.get("from").getAsString() + ":" +
                             item.get("to").getAsString() + ":" +
                             item.get("type").getAsString();
                observed.putIfAbsent(key, item);
            }
            if (truncated) {
                break;
            }
        }
        JsonArray values = new JsonArray();
        for (JsonObject item : observed.values()) {
            values.add(item);
        }
        facts.add("instruction_references", values);
        facts.addProperty("instruction_references_truncated", truncated);
        facts.addProperty("instructions_scanned", Math.min(scanned, MAX_INSTRUCTIONS));
    }

    private void addRelated(JsonObject facts, String name, Set<Function> related) throws Exception {
        List<Function> ordered = new ArrayList<>(related);
        ordered.sort((left, right) -> left.getEntryPoint().compareTo(right.getEntryPoint()));
        JsonArray values = new JsonArray();
        for (int index = 0; index < Math.min(ordered.size(), MAX_RELATED_FUNCTIONS); index++) {
            monitor.checkCancelled();
            Function target = ordered.get(index);
            JsonObject item = new JsonObject();
            item.addProperty("address", "0x" + target.getEntryPoint());
            item.addProperty("name", target.getName());
            values.add(item);
        }
        facts.add(name, values);
        facts.addProperty(name + "_truncated", ordered.size() > MAX_RELATED_FUNCTIONS);
    }

    @Override
    protected void run() throws Exception {
        String[] arguments = getScriptArgs();
        if (arguments.length < 2 || arguments.length % 2 != 0 || arguments.length > 64) {
            throw new IllegalArgumentException("expected 1-32 address/output pairs");
        }
        DecompInterface decompiler = new DecompInterface();
        try {
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("Ghidra decompiler could not open the program");
            }
            println("COPYAPP_BATCH_START " + (arguments.length / 2));
            for (int index = 0; index < arguments.length; index += 2) {
                Address address = toAddr(arguments[index]);
                Path output = Path.of(arguments[index + 1]);
                Function function = currentProgram.getFunctionManager().getFunctionAt(address);
                if (function == null) {
                    throw new IllegalArgumentException("no analyzed function begins at " + address);
                }
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                if (!result.decompileCompleted() || result.getDecompiledFunction() == null) {
                    throw new IllegalStateException("decompilation failed: " + result.getErrorMessage());
                }
                String pseudocode = result.getDecompiledFunction().getC();
                if (pseudocode == null || pseudocode.isBlank()) {
                    throw new IllegalStateException("decompiler returned empty pseudocode");
                }
                Files.writeString(output.resolve("pseudocode.txt"), pseudocode,
                                  StandardCharsets.UTF_8);
                Files.writeString(output.resolve("address.txt"),
                                  function.getEntryPoint().toString() + "\n", StandardCharsets.UTF_8);
                Files.writeString(output.resolve("name.txt"), function.getName() + "\n",
                                  StandardCharsets.UTF_8);
                Files.writeString(output.resolve("language.txt"),
                                  currentProgram.getLanguageID().toString() + "\n",
                                  StandardCharsets.UTF_8);
                Files.writeString(output.resolve("function-facts.json"),
                                  functionFacts(function).toString() + "\n", StandardCharsets.UTF_8);
                println("COPYAPP_DECOMPILE_COMPLETE " + function.getEntryPoint());
            }
            println("COPYAPP_BATCH_COMPLETE " + (arguments.length / 2));
        }
        finally {
            decompiler.dispose();
        }
    }
}
