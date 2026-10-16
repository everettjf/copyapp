#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: sh scripts/compose-calculator-report.sh OUTPUT_DIR" >&2
    exit 2
fi

cd "$(dirname "$0")/.."
.venv/bin/copyapp report \
    --case cases/calculator-xr-analysis-20261015 \
    --findings docs/calculator-findings.json \
    --feature-spec docs/calculator-feature-spec.json \
    --evidence ui.initial=cases/calculator-basic-addition-20261015/step-03-screenshot.jpg \
    --evidence ui.addition=cases/calculator-basic-addition-ready-20261015 \
    --evidence ui.result=cases/calculator-basic-addition-20261015/step-09-screenshot.jpg \
    --evidence ui.result_ocr=cases/calculator-basic-addition-20261015/result-ocr.json \
    --evidence ui.percent=cases/calculator-percent-original-20261015 \
    --evidence ui.percent_intermediate=cases/calculator-percent-original-20261015/step-10-screenshot.jpg \
    --evidence ui.percent_result=cases/calculator-percent-original-20261015/step-12-screenshot.jpg \
    --evidence ui.percent_intermediate_ocr=cases/calculator-ocr-20261015/percent-original-10.json \
    --evidence ui.percent_result_ocr=cases/calculator-ocr-20261015/percent-original-110.json \
    --evidence ui.repeat=cases/calculator-repeat-flow-original-20261015 \
    --evidence ui.repeat_first=cases/calculator-repeat-flow-original-20261015/playbook/step-07-screenshot.jpg \
    --evidence ui.repeat_second=cases/calculator-repeat-flow-original-20261015/playbook/step-09-screenshot.jpg \
    --evidence ui.view_tree=cases/calculator-view-tree-v4-20261015 \
    --evidence exp.ax_button=cases/calculator-button-model-experiment-20261015 \
    --evidence probe.unmatched_candidate=cases/calculator-button-candidates-20261015/candidates.json \
    --evidence probe.button_path=cases/calculator-direct-button-probe-v4-20261015 \
    --evidence rea.button_entry=cases/calculator-hopper-button-20261015 \
    --evidence rea.button_dispatch_hopper=cases/calculator-hopper-button-body-20261015 \
    --evidence rea.button_dispatch_ghidra=cases/calculator-ghidra-button-body-20261015 \
    --evidence rea.digit=cases/calculator-hopper-digit-20261015 \
    --evidence rea.operator=cases/calculator-hopper-operator-20261015 \
    --evidence rea.equals=cases/calculator-hopper-equals-20261015 \
    --evidence rea.evaluate=cases/calculator-hopper-evaluate-20261015 \
    --evidence rea.calculate_bridge=cases/calculator-hopper-calculate-bridge-20261015 \
    --evidence rea.root_ui=cases/calculator-hopper-root-ui-body-20261015 \
    --evidence rea.keypad_layout=cases/calculator-hopper-keypad-layout-body-20261015 \
    --out "$1"

.venv/bin/copyapp verify "$1"
