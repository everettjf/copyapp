import unittest
from unittest.mock import Mock, patch

from copyapp.experiment import ExperimentUI, _ictrl_label_in_region
from copyapp.ios_mcp import IOSMCPClient


class TapLabelRegionTest(unittest.TestCase):
    def test_ictrl_swipe_maps_exact_start_direction_and_distance(self):
        ui = object.__new__(ExperimentUI)
        ui.backend = "ictrl"
        ui.client = Mock()
        ui.client.call_ui.return_value = {"message": "Swiped"}
        ui.swipe(346, 280, 132, 280, 350, 20)
        ui.client.call_ui.assert_called_once_with("swipe", {
            "x": 346, "y": 280, "direction": "left",
            "distance": 214, "velocity": "normal"})

    def test_ictrl_uses_device_identity_channel_and_explicit_app_tree(self):
        ui = object.__new__(ExperimentUI)
        ui.backend = "ictrl"
        ui.bundle_id = "dev.copyapp.clockclone"
        ui.client = Mock()
        ui.client.call_ui.return_value = {"bundle_id": "dev.copyapp.clockclone",
                                          "source_channel": "ax", "source": "Clock"}
        ui.identity_client = Mock()
        with patch.object(IOSMCPClient, "text_json",
                          return_value={"bundleId": "dev.copyapp.clockclone"}):
            self.assertEqual(ui.frontmost(), "dev.copyapp.clockclone")
        ui.identity_client.call_ui.assert_called_once_with("get_frontmost_app")
        self.assertEqual(ui.observe()["source"], "Clock")
        ui.client.call_ui.assert_called_once_with("page_source", {
            "visible_only": True, "max_children": 50,
            "bundle_id": "dev.copyapp.clockclone"})

    def test_ictrl_rejects_wrong_app_page_source(self):
        ui = object.__new__(ExperimentUI)
        ui.backend = "ictrl"
        ui.bundle_id = "dev.copyapp.clockclone"
        ui.client = Mock()
        ui.client.call_ui.return_value = {"bundle_id": "com.apple.springboard",
                                          "source_channel": "ax", "source": "Clock"}
        with self.assertRaisesRegex(RuntimeError, "different App"):
            ui.observe()

    def test_chooses_keypad_zero_with_bounded_region(self):
        ui = object.__new__(ExperimentUI)
        ui.backend = "ios-mcp"
        ui.observe = Mock(return_value={"elements": [
            {"text": "0", "clickable": True,
             "rect": {"x": 20, "y": 225, "width": 360, "height": 100}},
            {"text": "0", "clickable": True,
             "rect": {"x": 16, "y": 737, "width": 184, "height": 85}},
        ]})
        ui.tap = Mock(return_value={"ok": True})
        with self.assertRaisesRegex(RuntimeError, "found 2"):
            ui.tap_label("0")
        self.assertEqual(ui.tap_label("0", [0, 700, 210, 830])["match"]["y"], 779.5)
        ui.tap.assert_called_once_with(108, 779.5)

    def test_ictrl_ref_outside_region_is_rejected_before_tap(self):
        ui = object.__new__(ExperimentUI)
        ui.backend = "ictrl"
        ui.client = Mock()
        ui.client.call_ui.side_effect = [self._page(),
            {"exists": True, "hittable": True, "ref": "display", "element_type": "Button",
             "center_x": 108, "center_y": 275}]
        with self.assertRaisesRegex(RuntimeError, "reference differs"):
            ui.tap_label("0", [0, 700, 210, 830], "dev.example.calculator")
        self.assertEqual(ui.client.call_ui.call_count, 2)

    @staticmethod
    def _page():
        return {"bundle_id": "dev.example.calculator", "truncated": False,
                "coordinate_space": "points", "source":
                "StaticText, label: '0', {{20, 225}, {360, 100}}\n"
                "Button, label: '0', {{16, 737}, {184, 85}}\n"
                "StaticText, label: '0', {{45, 760}, {30, 40}}"}

    def test_ictrl_bounded_label_uses_matching_ref(self):
        ui = object.__new__(ExperimentUI)
        ui.backend = "ictrl"
        ui.client = Mock()
        ui.client.call_ui.side_effect = [self._page(),
            {"exists": True, "hittable": True, "ref": "key-zero", "element_type": "Button",
             "center_x": 108, "center_y": 779.5}, {"ok": True}]
        result = ui.tap_label("0", [0, 700, 210, 830], "dev.example.calculator")
        self.assertEqual(result["match"]["ref"], "key-zero")
        self.assertEqual(ui.client.call_ui.call_args_list[1].args,
                         ("find_element", {"element_id": "0",
                                           "bundle_id": "dev.example.calculator",
                                           "element_type": "Button"}))
        ui.client.call_ui.assert_any_call("tap", {"ref": "key-zero"})

    def test_ictrl_bounded_label_rejects_two_buttons(self):
        page = self._page()
        page["source"] += "\nButton, label: '0', {{210, 737}, {85, 85}}"
        with self.assertRaisesRegex(RuntimeError, "found 2"):
            _ictrl_label_in_region(page, "0", [0, 700, 414, 830],
                                   "dev.example.calculator")

    def test_ictrl_unbounded_ref_needs_no_center_coordinates(self):
        ui = object.__new__(ExperimentUI)
        ui.backend = "ictrl"
        ui.client = Mock()
        ui.client.call_ui.side_effect = [
            {"exists": True, "hittable": True, "ref": "key-zero", "label": "0"},
            {"ok": True},
        ]
        self.assertEqual(ui.tap_label("0")["match"]["ref"], "key-zero")
        ui.client.call_ui.assert_any_call("tap", {"ref": "key-zero"})
