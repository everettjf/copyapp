# Contributing to Copy APP

**Language:** English | [简体中文](CONTRIBUTING.zh-CN.md)

Thanks for helping make iOS app analysis more reproducible. Copy APP joins phone observations, native analysis, a reviewed report and an independently built app. Contributions should improve one of those links while keeping its evidence traceable.

## Good first contributions

- Fix a reproducible setup, USB tunnel or UI backend issue.
- Add a bounded playbook or a parser test with a synthetic fixture.
- Improve error messages and onboarding guidance for a real failure.
- Translate a README overview or correct an existing translation.
- Add an optional analyzer without making it mandatory for the default workflow.

## Development workflow

1. Read [README.md](README.md), [the workflow guide](docs/copy-workflow.md) and [AGENTS.md](AGENTS.md). Open a focused issue for a design change that affects case schemas or device privileges.
2. Reproduce the issue with an exact command and a new output case. Record the device model, iOS version, jailbreak, Xcode and relevant tool versions. When no device is needed, use a synthetic fixture.
3. Make the smallest change that preserves case provenance and the meaning of existing verification gates. Keep optional tools optional.
4. Run `PYTHONPYCACHEPREFIX=/tmp/copyapp-pycache .venv/bin/python -m unittest discover -s tests`. For a generated case, run `.venv/bin/copyapp verify <CASE>`. If a change touches device control, report the real device and selected flows you tested; say which versions remain untested.
5. Submit a PR describing the behavior changed, evidence, tests and limitations. Link the relevant docs. Do not present an Agent exit, successful build or hash check alone as functional equivalence.

## Repository map

| Path | Purpose |
| --- | --- |
| `copyapp/` | Mac CLI, acquisition, analysis, orchestration and verification. |
| `device/ios-mcp/` | Rootless phone UI service. |
| `vendor/ictrl/` | Attributed optional iCTRL source and build. |
| `skills/` | Coding-agent workflows and handoffs. |
| `examples/rebuild/` | Independent example implementations and experimental probes. |
| `rebuild/` | Suggested local output path for a new, unreviewed rebuild. |
| `tests/` and `fixture/` | Automated checks and known-source fixtures. |
| `examples/report-inputs/` | Historical pilot JSON inputs; not current device reports. |
| `docs/` | Current setup, architecture, workflow, support limits, release note and localized README overviews. |
| `cases/` | Local evidence and credentials; ignored by Git. |

Do not commit raw IPAs, device screenshots, sandbox exports, pairing records, credentials or account data. Use synthetic fixtures or sanitized summaries in reviews. Preserve upstream licenses, NOTICE files and provenance when adapting code.

## Translation notes

English `README.md` and Chinese `README.zh-CN.md` summarize setup and link to the full guides. Other localized README pages should accurately describe the named iOS 16, 17 and 26 selected-flow results, retain links to the current setup and contribution guides, and avoid general device or whole-app compatibility claims. Translation-only changes do not require a connected phone; check links, code blocks and technical names.
