# Examples

These are source examples, not prebuilt IPAs or full-app replicas. Read each project's README and the [current device status](../docs/current-status.md) before using a result as evidence. Build products, signed packages, raw device cases and credentials stay out of Git.

- [Independent iOS app sources and probes](rebuild/README.md)
- [Pilot report input formats](report-inputs/README.md)
- [Owned macOS behavior fixture](macos/BehaviorFixture/README.md) — an original
  AppKit sample for development acceptance, not a rebuilt delivery.
- [Independent macOS editor](macos/IndependentEditor/README.md) — selected file,
  window and persistence behavior with a verified named-guest delivery.
- [Independent Stocks App source](macos/Stocks/README.md) — runnable AppKit demo,
  build script and three original-flow playbooks. Illustrative offline data;
  bounded prototype grade 81/100, with visual differences retained.

New jobs default to `output/<app>-<unique-run>/project/` and sibling `evidence/`.
Curated iOS sources live under `examples/rebuild/`; macOS sources under
`examples/macos/`. The legacy `rebuild/<NEW_PROJECT>` workspace remains supported.
