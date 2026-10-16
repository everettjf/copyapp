#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: sh scripts/compose-pilot-report.sh compass|fixture OUTPUT_DIR" >&2
    exit 2
fi

cd "$(dirname "$0")/.."
pilot=$1
output=$2

case "$pilot" in
    compass)
        .venv/bin/copyapp report \
            --case cases/compass-xr-mcp-onepass-20261015 \
            --findings docs/compass-findings.json \
            --feature-spec docs/compass-feature-spec.json \
            --evidence rea.update_display=cases/compass-xr-rea-update-display-20261015 \
            --evidence rea.tap_bearing=cases/compass-bearing-candidate-rea-20261015 \
            --evidence rea.tap_bearing_hopper=cases/compass-hopper-tapped-20261015 \
            --evidence rea.set_bearing=cases/compass-ghidra-set-bearing-20261015 \
            --evidence rea.set_bearing_hopper=cases/compass-hopper-set-bearing-20261015 \
            --evidence rea.unset_bearing=cases/compass-ghidra-unset-bearing-20261015 \
            --evidence rea.unset_bearing_hopper=cases/compass-hopper-unset-bearing-20261015 \
            --evidence rea.update_layer=cases/compass-ghidra-update-layer-20261015 \
            --evidence rea.update_layer_hopper=cases/compass-hopper-update-layer-20261015 \
            --evidence rea.bearing_layout=cases/compass-ghidra-bearing-layout-20261015 \
            --evidence rea.bearing_layout_hopper=cases/compass-hopper-bearing-layout-20261015 \
            --evidence rea.bearing_init=cases/compass-ghidra-bearing-init-20261015 \
            --evidence rea.bearing_heading_setter=cases/compass-ghidra-set-compass-heading-v3-20261015 \
            --evidence rea.start_motion=cases/compass-xr-rea-start-motion-20261015 \
            --evidence rea.open_maps=cases/compass-xr-rea-open-maps-20261015 \
            --evidence rea.auth_change=cases/compass-ghidra-auth-change-20261015 \
            --evidence rea.start_location=cases/compass-ghidra-start-location-20261015 \
            --evidence rea.set_user_location=cases/compass-ghidra-user-location-20261015 \
            --evidence rea.hide_coordinate=cases/compass-ghidra-hide-coordinate-20261015 \
            --evidence rea.coordinate_label=cases/compass-ghidra-coordinate-label-20261015 \
            --evidence rea.place_labels=cases/compass-ghidra-place-labels-20261015 \
            --evidence exp.bearing=cases/experiment-original-bearing-chain-20261015 \
            --evidence exp.bearing_unset=cases/compass-bearing-toggle-1-20261015 \
            --evidence exp.bearing_set=cases/compass-bearing-toggle-2-20261015 \
            --evidence exp.binding_unset=cases/compass-binding-probe-20261015 \
            --evidence exp.binding_set=cases/compass-binding-set-probe-20261015 \
            --evidence exp.maps=cases/experiment-original-maps-retry-20261015 \
            --evidence probe.maps_url=cases/compass-maps-url-original-stable-20261015/experiment.json \
            --evidence probe.maps_screen=cases/compass-maps-url-original-stable-20261015/after.jpg \
            --evidence probe.north=cases/compass-motion-frame-20261015/result.json \
            --evidence probe.bearing_offset=cases/compass-offset-original-radii-20261015/experiment.json \
            --evidence probe.bearing_offset_image=cases/compass-offset-original-radii-20261015/offset.jpg \
            --evidence ui.location_permission_never=cases/settings-original-compass-permission-never-20261015.jpg \
            --evidence ui.location_denied_original=cases/compass-original-location-denied-unlocked-20261015.jpg \
            --out "$output"
        ;;
    fixture)
        .venv/bin/copyapp report \
            --case cases/fixture-xr-analysis-20261015 \
            --findings docs/fixture-findings.json \
            --feature-spec docs/fixture-feature-spec.json \
            --evidence ui.counter_before=cases/fixture-xr-ui-20261015/counter-before.jpg \
            --evidence ui.counter_after=cases/fixture-xr-ui-20261015/counter-after.jpg \
            --evidence ui.counter_view_tree=cases/fixture-swiftui-counter-view-tree-v2-20261015 \
            --evidence ui.notes_before=cases/fixture-xr-ui-20261015/notes-before.jpg \
            --evidence ui.notes_after=cases/fixture-xr-ui-20261015/notes-after.jpg \
            --evidence ui.catalog=cases/fixture-xr-ui-20261015/catalog.jpg \
            --evidence data.prefs=cases/fixture-xr-ui-20261015/prefs-after-counter.plist \
            --evidence data.sqlite=cases/fixture-xr-ui-20261015/fixture-notes.sqlite \
            --evidence data.sandbox_diff=cases/fixture-sandbox-diff-with-action-20261015 \
            --evidence exp.notes=cases/fixture-xr-notes-trace-20261015 \
            --evidence exp.catalog=cases/fixture-xr-catalog-trace-20261015 \
            --evidence rea.counter=cases/fixture-xr-rea-counter-increment-20261015 \
            --evidence rea.add_note=cases/fixture-xr-rea-add-note-20261015 \
            --evidence rea.note_body=cases/fixture-xr-rea-add-note-body-20261015 \
            --evidence rea.note_store=cases/fixture-xr-rea-note-store-20261015 \
            --evidence rea.sqlite_insert=cases/fixture-xr-rea-sqlite-insert-20261015 \
            --evidence rea.catalog=cases/fixture-xr-rea-catalog-init-20261015 \
            --evidence rea.share_hopper=cases/rea-hopper-normal-session-20261015/xr-share \
            --evidence inv.counter=cases/fixture-counter-one-command-investigation-v2-20261015 \
            --evidence inv.notes=cases/fixture-notes-autoselect-investigation-20261015 \
            --evidence inv.catalog=cases/fixture-catalog-autoselect-investigation-20261015 \
            --evidence app.all=cases/fixture-app-investigation-20261015 \
            --evidence flow.counter=cases/fixture-counter-comparable-ready-flow-20261015 \
            --evidence flow.notes=cases/fixture-notes-comparable-ready-flow-20261015 \
            --evidence flow.catalog=cases/fixture-catalog-comparable-ready-flow-20261015 \
            --out "$output"
        ;;
    *)
        echo "unknown pilot: $pilot" >&2
        exit 2
        ;;
esac

.venv/bin/copyapp verify "$output"
