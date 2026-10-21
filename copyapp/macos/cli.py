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
    report_source = report.add_mutually_exclusive_group(required=True)
    report_source.add_argument("--flow", action="append", help="SCENARIO_ID=MAC_PLAYBOOK_CASE")
    report_source.add_argument("--discovery", type=Path, help="accepted Mac discovery case; use its exact replayed flows")
    report.add_argument("--review", required=True, type=Path)
    report.add_argument("--out", required=True, type=Path)
    report.add_argument("--data", action="append", help="DATA_ID=MAC_DATA_SCHEMA_CASE; structure citations only")
    plan = sub.add_parser("rebuild-plan", help="freeze known scope and prepare a current-agent implementation task")
    plan.add_argument("--report", required=True, type=Path)
    plan.add_argument("--bundle", required=True, help="separate Bundle ID for the independent rebuild")
    plan.add_argument("--app-path", required=True, help="separate target .app path in the guest")
    plan.add_argument("--project", required=True, type=Path)
    plan.add_argument("--capability", action="append", required=True, help="explicit reviewed target capability ID")
    plan.add_argument("--out", required=True, type=Path)
    build = sub.add_parser("build-app", help="build and sign independent Mac source pinned to a verified rebuild plan")
    build.add_argument("--plan", required=True, type=Path)
    build.add_argument("--swift-source", action="append", default=[], help="project-relative Swift file (repeatable)")
    build.add_argument("--info-plist", help="project-relative bundle Info.plist for a direct Swift build")
    build.add_argument("--resources", help="project-relative resource directory for a direct Swift build")
    build.add_argument("--xcode-project", help="project-relative .xcodeproj; use with --scheme")
    build.add_argument("--scheme")
    build.add_argument("--configuration", default="Debug")
    build.add_argument("--deployment-target", default="14.0")
    build.add_argument("--signing-identity", default="-")
    build.add_argument("--timeout", type=float, default=1200)
    build.add_argument("--out", required=True, type=Path)
    install = sub.add_parser("install", help="install a verified independent build into its registered guest; never replaces an App")
    install.add_argument("--build", required=True, type=Path)
    install.add_argument("--timeout", type=float, default=60)
    install.add_argument("--out", required=True, type=Path)
    check_plan = sub.add_parser("check-plan", help="freeze UI conditions and masks before fresh paired runs")
    check_plan.add_argument("--install", required=True, type=Path)
    check_plan.add_argument("--conditions", required=True, type=Path)
    check_plan.add_argument("--rounds", type=int, default=3)
    check_plan.add_argument("--out", required=True, type=Path)
    check = sub.add_parser("rebuild-check", help="acquire the installed rebuild and replay each original/rebuilt flow; no automatic retries")
    check.add_argument("--plan", required=True, type=Path)
    check.add_argument("--timeout", type=float, default=30)
    check.add_argument("--out", required=True, type=Path)
    visual = sub.add_parser("visual-review", help="bind explicit full-screen judgments to every paired Mac image")
    visual.add_argument("--check", required=True, type=Path)
    visual.add_argument("--judgments", required=True, type=Path)
    visual.add_argument("--out", required=True, type=Path)
    delivery = sub.add_parser("delivery", help="bind selected Mac behavior delivery to source, install, paired checks and capability review")
    delivery.add_argument("--visual-review", required=True, type=Path)
    delivery.add_argument("--coverage", required=True, type=Path)
    delivery.add_argument("--out", required=True, type=Path)
    share = sub.add_parser("share-probe", help="publish a nonce for a manual guest Finder shared-file probe")
    share.add_argument("--vm-directory", required=True, type=Path)
    share.add_argument("--out", required=True, type=Path)
    reply = sub.add_parser("share-probe-check", help="record the returned nonce bytes; does not establish runtime identity")
    reply.add_argument("--request", required=True, type=Path)
    reply.add_argument("--reviewer", required=True)
    reply.add_argument("--notes", required=True)
    reply.add_argument("--out", required=True, type=Path)
    imported = sub.add_parser("import-app", help="snapshot and statically index one App from a ZIP or read-only DMG; no execution")
    imported.add_argument("--source", required=True, type=Path)
    imported.add_argument("--app-relative", help="explicit .app path within an ambiguous distribution")
    imported.add_argument("--out", required=True, type=Path)
    discovery = sub.add_parser("discover-check", help="accept three to twelve reviewed representative Mac flow replays")
    discovery.add_argument("--flow", action="append", required=True, help="SCENARIO_ID=MAC_PLAYBOOK_CASE")
    discovery.add_argument("--review", required=True, type=Path)
    discovery.add_argument("--out", required=True, type=Path)
    data = sub.add_parser("data-file", help="capture one explicitly selected App data file; not a complete or atomic DB snapshot")
    data.add_argument("--acquisition", required=True, type=Path)
    data.add_argument("--location", required=True, choices=("sandbox", "preferences", "support"))
    data.add_argument("--path", required=True, help="canonical file path relative to the selected guest Library location")
    data.add_argument("--timeout", type=float, default=60)
    data.add_argument("--out", required=True, type=Path)
    schema = sub.add_parser("data-schema", help="extract key/type or SQLite metadata from one verified Mac data file")
    schema.add_argument("--data", required=True, type=Path)
    schema.add_argument("--format", choices=("plist", "sqlite"), required=True)
    schema.add_argument("--out", required=True, type=Path)
    inventory = sub.add_parser("snapshot-inspect", help="record bounded public snapshot metadata without a VM mutation")
    inventory.add_argument("--vm-directory", type=Path, required=True)
    inventory.add_argument("--out", type=Path, required=True)
    take = sub.add_parser("snapshot-take", help="take one ChatComputer-owned snapshot and recheck fresh sessions")
    take.add_argument("--environment", type=Path, required=True)
    take.add_argument("--timeout", type=float, default=120)
    take.add_argument("--out", type=Path, required=True)
    restore = sub.add_parser("snapshot-restore", help="restore a pinned Copy APP snapshot; always retain a safety snapshot")
    restore.add_argument("--snapshot", type=Path, required=True)
    restore.add_argument("--timeout", type=float, default=120)
    restore.add_argument("--out", type=Path, required=True)


def named_flows(items: list) -> dict:
    flows = {}
    for item in items or []:
        key, separator, value = item.partition("=")
        if not separator or not value or key in flows:
            raise ValueError("use each SCENARIO_ID=MAC_PLAYBOOK_CASE once")
        flows[key] = Path(value)
    return flows


def run(args) -> int:
    if args.mac_command == "snapshot-inspect":
        from copyapp.macos.snapshots import snapshot_inventory
        print(snapshot_inventory(args.vm_directory, args.out))
        return 0
    if args.mac_command in {"snapshot-take", "snapshot-restore"}:
        from copyapp.macos.snapshots import snapshot_operation
        action = "take" if args.mac_command == "snapshot-take" else "restore"
        print(snapshot_operation(args.environment if action == "take" else args.snapshot, args.out, action, args.timeout))
        return 0
    if args.mac_command == "data-schema":
        from copyapp.macos.data_schema import data_schema
        print(data_schema(args.data, args.format, args.out))
        return 0
    if args.mac_command == "data-file":
        from copyapp.macos.data import data_file
        print(data_file(args.acquisition, args.location, args.path, args.out, args.timeout))
        return 0
    if args.mac_command == "discover-check":
        from copyapp.macos.discovery import discover_check
        print(discover_check(named_flows(args.flow), args.review, args.out))
        return 0
    if args.mac_command == "import-app":
        from copyapp.macos.distribution import import_app
        print(import_app(args.source, args.out, args.app_relative))
        return 0
    if args.mac_command == "share-probe":
        from copyapp.macos.share import share_request
        print(share_request(args.vm_directory, args.out))
        return 0
    if args.mac_command == "share-probe-check":
        from copyapp.macos.share import share_result
        print(share_result(args.request, args.out, args.reviewer, args.notes))
        return 0
    if args.mac_command == "delivery":
        from copyapp.macos.delivery import delivery
        print(delivery(args.visual_review, args.coverage, args.out))
        return 0
    if args.mac_command == "visual-review":
        from copyapp.macos.visual import visual_review
        print(visual_review(args.check, args.judgments, args.out))
        return 0
    if args.mac_command == "check-plan":
        from copyapp.macos.checks import check_plan
        print(check_plan(args.install, args.conditions, args.out, args.rounds))
        return 0
    if args.mac_command == "rebuild-check":
        from copyapp.macos.checks import rebuild_check
        print(rebuild_check(args.plan, args.out, args.timeout))
        return 0
    if args.mac_command == "install":
        from copyapp.macos.install import install_app
        print(install_app(args.build, args.out, args.timeout))
        return 0
    if args.mac_command == "build-app":
        from copyapp.macos.build import build_app, recipe_for
        recipe = recipe_for(swift_sources=args.swift_source, info_plist=args.info_plist,
                            resources=args.resources, xcode_project=args.xcode_project, scheme=args.scheme,
                            configuration=args.configuration, signing_identity=args.signing_identity,
                            deployment_target=args.deployment_target)
        print(build_app(args.plan, args.out, recipe, args.timeout))
        return 0
    if args.mac_command == "report":
        from copyapp.macos.report import report
        print(report(named_flows(args.flow), args.review, args.out, discovery=args.discovery, data=named_flows(args.data)))
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
