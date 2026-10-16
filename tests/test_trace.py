import unittest

from copyapp.trace import parse_branch_register, parse_method, trace_script


class TraceScriptTest(unittest.TestCase):
    def test_selector_with_colons_is_preserved(self):
        method = parse_method("CompassController::locationManager:didUpdateLocations:")
        self.assertEqual(method, ("CompassController", "locationManager:didUpdateLocations:"))
        script = trace_script([method])
        self.assertIn('"selector": "locationManager:didUpdateLocations:"', script)

    def test_invalid_method_spec_is_rejected(self):
        for value in ("CompassController", "::updateDisplay:", "CompassController::"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_method(value)

    def test_experiment_streams_hits_without_post_tap_rpc(self):
        script = trace_script([("CompassController", "_openMaps")], stream_hits=True)
        self.assertIn('const hit = {type: "method_hit", index: index}', script)
        self.assertIn("const streamHits = true;", script)

    def test_selected_raw_argument_is_read_at_both_entries(self):
        script = trace_script([("CalculatorModel", "buttonPressed:")],
                              stream_hits=True, arg2_u32_indices=[0])
        self.assertIn("const arg2U32Indices = new Set([0]);", script)
        self.assertEqual(script.count("hit.arg2_u32 = args[2].toUInt32()"), 2)
        with self.assertRaises(ValueError):
            trace_script([("CalculatorModel", "buttonPressed:")],
                         arg2_u32_indices=[1])

    def test_branch_hooks_require_static_app_binding(self):
        method = [("CalculatorModel", "buttonPressed:")]
        with self.assertRaises(ValueError):
            trace_script(method, stream_hits=True, branch_offsets=[0x14840])
        script = trace_script(method, stream_hits=True, static_targets=[{
            "index": 0, "class": "CalculatorModel", "selector": "buttonPressed:",
            "binary_name": "Calculator", "app_dir": "Calculator.app", "offset": 0xeb0c}],
            branch_offsets=[0xeb5c, 0x1266c])
        self.assertIn("const branchOffsets = [60252, 75372];", script)
        self.assertIn("send({type: 'branch_hit', index: index})", script)

    def test_selected_branch_return_captures_raw_u32_only(self):
        method = [("Demo", "pressed:")]
        target = [{"index": 0, "class": "Demo", "selector": "pressed:",
                   "binary_name": "Demo", "app_dir": "Demo.app", "offset": 0x100}]
        script = trace_script(method, stream_hits=True, static_targets=target,
                              branch_offsets=[0x200, 0x300],
                              branch_return_u32_offsets=[0x300])
        self.assertIn("const branchReturnU32Offsets = new Set([768]);", script)
        self.assertIn("value: retval.toUInt32()", script)
        with self.assertRaisesRegex(ValueError, "selected branch"):
            trace_script(method, static_targets=target, branch_offsets=[0x200],
                         branch_return_u32_offsets=[0x300])

    def test_selected_branch_register_maps_pointer_within_app_image(self):
        self.assertEqual(parse_branch_register("0x400:x19"), (0x400, "x19"))
        with self.assertRaises(ValueError):
            parse_branch_register("0x400:sp")
        target = [{"index": 0, "class": "Demo", "selector": "pressed:",
                   "binary_name": "Demo", "app_dir": "Demo.app", "offset": 0x100}]
        script = trace_script([("Demo", "pressed:")], stream_hits=True,
                              static_targets=target, branch_offsets=[0x400],
                              branch_registers=[(0x400, "x19")])
        self.assertIn('const branchRegisters = [{"offset": 1024, "register": "x19"}];', script)
        self.assertIn("this.context[item.register].strip('ia')", script)
        self.assertIn("target_offset: pointer.sub(module.base).toString()", script)
        with self.assertRaisesRegex(ValueError, "selected branch"):
            trace_script([("Demo", "pressed:")], static_targets=target,
                         branch_offsets=[0x400], branch_registers=[(0x500, "x19")])


if __name__ == "__main__":
    unittest.main()
