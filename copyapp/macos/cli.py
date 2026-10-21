"""Separate macOS entry points; do not reinterpret the existing iOS arguments."""

import argparse
from pathlib import Path


def configure(parser: argparse.ArgumentParser):
    sub = parser.add_subparsers(dest="mac_command", required=True)
    probe = sub.add_parser("doctor", help="record ChatComputer transport readiness (not exact App readiness)")
    probe.add_argument("--out", required=True, type=Path)
    probe.add_argument("--chatcomputer", default="chatcomputer", help="installed ChatComputer executable")
    probe.add_argument("--data-dir", type=Path, help="explicit existing ChatComputer data directory")
    probe.add_argument("--timeout", type=float, default=30)
    index = sub.add_parser("inspect", help="snapshot and index a local arm64 macOS .app; no launch")
    index.add_argument("--app", required=True, type=Path)
    index.add_argument("--out", required=True, type=Path)
    setup = sub.add_parser("build-collector", help="build the bounded guest collector; does not install or grant permissions")
    setup.add_argument("--out", required=True, type=Path)
    setup.add_argument("--signing-identity", default="-", help="stable signing identity; default is ad-hoc")
    deploy = sub.add_parser("prepare-collector", help="prepare a verified helper for sharing; does not install it")
    deploy.add_argument("--build", required=True, type=Path)
    deploy.add_argument("--out", required=True, type=Path)
    deploy.add_argument("--request-accessibility", action="store_true",
                        help="launcher requests guest Accessibility permission; never grants it automatically")
    connect = sub.add_parser("connect", help="register an exact ready VM with a running collector")
    connect.add_argument("--vm-directory", required=True, type=Path)
    connect.add_argument("--collector-build", required=True, type=Path)
    connect.add_argument("--chatcomputer", default="chatcomputer")
    connect.add_argument("--timeout", type=float, default=30)
    connect.add_argument("--out", required=True, type=Path)
    observe = sub.add_parser("observe", help="collect exact guest App identity and optionally AX/screenshot evidence")
    observe.add_argument("--environment", required=True, type=Path)
    observe.add_argument("--app-path", required=True, help="absolute .app path inside the guest")
    observe.add_argument("--bundle", required=True)
    observe.add_argument("--ax", action="store_true", help="requires collector Accessibility permission in the guest")
    observe.add_argument("--timeout", type=float, default=30)
    observe.add_argument("--out", required=True, type=Path)
    acquire = sub.add_parser("acquire", help="collect and index a stable exact guest .app snapshot")
    acquire.add_argument("--environment", required=True, type=Path)
    acquire.add_argument("--app-path", required=True)
    acquire.add_argument("--bundle", required=True)
    acquire.add_argument("--timeout", type=float, default=60)
    acquire.add_argument("--out", required=True, type=Path)
    replay = sub.add_parser("playbook", help="replay one bounded, guest-package-bound Mac flow")
    replay.add_argument("--acquisition", required=True, type=Path)
    replay.add_argument("--script", required=True, type=Path)
    replay.add_argument("--timeout", type=float, default=30)
    replay.add_argument("--out", required=True, type=Path)
    report = sub.add_parser("report", help="bind a reviewed behavior specification to verified Mac flow evidence")
    report.add_argument("--flow", action="append", required=True, help="SCENARIO_ID=MAC_PLAYBOOK_CASE")
    report.add_argument("--review", required=True, type=Path)
    report.add_argument("--out", required=True, type=Path)
    plan = sub.add_parser("rebuild-plan", help="freeze known scope and prepare a current-agent implementation task")
    plan.add_argument("--report", required=True, type=Path)
    plan.add_argument("--bundle", required=True, help="separate Bundle ID for the independent rebuild")
    plan.add_argument("--app-path", required=True, help="separate target .app path in the guest")
    plan.add_argument("--project", required=True, type=Path)
    plan.add_argument("--capability", action="append", required=True, help="explicit reviewed target capability ID")
    plan.add_argument("--out", required=True, type=Path)


def run(args) -> int:
    if args.mac_command == "report":
        from copyapp.macos.report import report
        flows = {}
        for item in args.flow:
            key, separator, value = item.partition("=")
            if not separator or not value or key in flows:
                raise ValueError("use each SCENARIO_ID=MAC_PLAYBOOK_CASE once")
            flows[key] = Path(value)
        print(report(flows, args.review, args.out))
        return 0
    if args.mac_command == "rebuild-plan":
        from copyapp.macos.rebuild import rebuild_plan
        print(rebuild_plan(args.report, args.bundle, args.app_path, args.project, args.capability, args.out))
        return 0
    if args.mac_command == "playbook":
        from copyapp.macos.playbook import run_playbook
        print(run_playbook(args.acquisition, args.script, args.out, args.timeout))
        return 0
    if args.mac_command == "acquire":
        from copyapp.macos.acquire import acquire_app
        print(acquire_app(args.environment, args.app_path, args.bundle, args.out, args.timeout))
        return 0
    if args.mac_command == "observe":
        from copyapp.macos.observation import observe_app
        print(observe_app(args.environment, args.app_path, args.bundle, args.out,
                          ax=args.ax, timeout=args.timeout))
        return 0
    if args.mac_command == "connect":
        from copyapp.macos.environment import register_environment
        print(register_environment(args.vm_directory, args.collector_build, args.out,
                                   args.chatcomputer, args.timeout))
        return 0
    if args.mac_command == "prepare-collector":
        from copyapp.macos.deploy import prepare_collector
        print(prepare_collector(args.build, args.out, args.request_accessibility))
        return 0
    if args.mac_command == "build-collector":
        from copyapp.macos.setup import build_collector
        print(build_collector(args.out, args.signing_identity))
        return 0
    if args.mac_command == "doctor":
        from copyapp.macos.doctor import doctor
        root, ready = doctor(args.out, args.chatcomputer, args.data_dir, args.timeout)
        print(root)
        print("ChatComputer transport: " + ("ready" if ready else "needs setup"))
        print("Exact App identity / analysis / rebuild: not yet checked")
        return 0 if ready else 1
    if args.mac_command == "inspect":
        from copyapp.macos.package import index_app
        print(index_app(args.app, args.out))
        return 0
    raise ValueError("unsupported macOS command")
