# Independent app examples

Each directory contains original project source or an experimental probe. The name is not a claim of complete app equivalence. Only the named device and selected flows in the linked case documentation have been checked; see [current status](../../docs/current-status.md).

| Example | Purpose |
| --- | --- |
| [NotesClone](NotesClone/README.md) | iOS 16 Notes selected flows; scoped folder, note and search behavior. |
| [CalculatorIOS17Fresh](CalculatorIOS17Fresh/README.md) | iOS 17 Calculator selected arithmetic flows and paired playbooks. |
| [ClockIOS26](ClockIOS26/README.md) | iOS 26 Clock selected Stopwatch flow. |
| [CompassClone](CompassClone/) | Compass pilot source and playbooks. |
| [CalculatorClone](CalculatorClone/), [CalculatorFreshProbe](CalculatorFreshProbe/), [CalculatorExternalAgent](CalculatorExternalAgent/) | Earlier Calculator implementations and agent probes. |
| [ClockClone](ClockClone/), [ClockCurrentProbe](ClockCurrentProbe/), [ClockCurrentAutoProbe](ClockCurrentAutoProbe/) | Earlier Clock implementations and probes. |
| [DeepSeekClone](DeepSeekClone/), [FixtureClone](FixtureClone/), [PodcastsFreshProbe](PodcastsFreshProbe/), [TranslateFreshProbe](TranslateFreshProbe/) | Target-specific experiments and fixtures. |

Run `xcodegen generate --spec project.yml` from the selected directory when the generated Xcode project is absent or stale. For projects with `package.sh`, run the script from that directory and inspect its signing requirements. Examples do not include the local `cases/` needed to reproduce device claims. Use a new output directory for your own app rather than editing a published example in place.
