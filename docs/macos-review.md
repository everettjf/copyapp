# Mac behavior review contract

This is the input contract for `copyapp mac report` on the development branch.
It does not change iOS report schemas or claim native function analysis.

First collect and verify one to twelve `mac playbook` cases. Each case must start
with launch, finish successfully and contain at least one explicit `expect_text`,
`expect_file` or `expect_stopped` assertion. All report flows must use the same
acquired package hash and exact registered environment. Their observations can be
from different times; the report does not make them simultaneous.

The current agent reads each flow's raw evidence and writes a review JSON like this.
Replace the script hash with SHA-256 of the case's saved `playbook.json`; flow IDs
must match its `scenario_id`. Citation paths must be recorded files under `steps/`
inside that flow case. Use actual observations rather than the example's claims.

```json
{
  "schema_version": 2,
  "platform": "macos",
  "scope": "behavior_analysis",
  "reviewer": "current-agent",
  "summary": "The selected text editing flow has an asserted output file.",
  "findings": [
    {
      "id": "saved-text",
      "certainty": "observed",
      "statement": "The captured output file contains the expected text.",
      "evidence": [{"flow_id": "edit-save", "path": "steps/05/output.bin"}]
    }
  ],
  "flows": [
    {
      "id": "edit-save",
      "source_script_sha256": "REPLACE_WITH_SAVED_PLAYBOOK_SHA256",
      "expected_behavior": "Edit and save the selected text.",
      "findings": ["saved-text"]
    }
  ],
  "capabilities": [
    {
      "id": "editing",
      "title": "Edit and save text",
      "flow_ids": ["edit-save"],
      "disposition": "available",
      "reason": "The selected flow has output assertions."
    },
    {
      "id": "printing",
      "title": "Printing",
      "flow_ids": [],
      "disposition": "deferred",
      "reason": "Identified in the known inventory but not exercised."
    }
  ],
  "inventory_note": "This is a reviewed known-capability inventory, not a complete census of the App.",
  "unknowns": ["Other document formats and unobserved menu actions remain unknown."]
}
```

Use `certainty: inferred` for an interpretation supported by the linked evidence.
Unknown behavior belongs in the nonempty `unknowns` list. Capability dispositions
are `available`, `deferred` or `blocked`; explain each and link available
capabilities to reviewed flows. IDs use ASCII letters, digits, `_` and `-`, with
at most 80 characters. The same review must cover exactly the supplied flows.

```sh
.venv/bin/copyapp mac report --flow edit-save=cases/mac-edit-save \
  --review cases/mac-review.json --out cases/mac-report
.venv/bin/copyapp verify cases/mac-report
.venv/bin/copyapp mac rebuild-plan --report cases/mac-report \
  --bundle dev.example.IndependentEditor \
  --app-path "<GUEST_INSTALL_ROOT>/IndependentEditor.app" \
  --project rebuild/IndependentEditor --capability editing \
  --out cases/mac-rebuild-plan
.venv/bin/copyapp verify cases/mac-rebuild-plan
```

The report preserves its source cases, reviewed JSON, hashed citations, readable
`report.md` and `feature-spec.json`. Its validator checks provenance and structure;
the reviewer owns interpretation and inventory completeness.

Use the registered environment's `environment.json` → `install_root` for
`<GUEST_INSTALL_ROOT>`; do not substitute the host's home directory. With the current
collector it normally names the guest's `~/Applications/CopyAppRebuilds`. The guest
installer accepts a new App directly inside that pinned root and never replaces
an existing file, directory or symbolic link.

The rebuild plan freezes the full known inventory and explicit target capability
IDs before implementation. Deferred or blocked entries cannot be selected without
a new review. It selects all flows linked to the target capabilities and records
omitted report flows. Generated scripts change only the App path and Bundle ID.
If the example targets one of two known capabilities, the target is 50% of that
known inventory; verified coverage and flow pass rate remain unavailable.

Read the generated `TASK.md` to continue independent implementation. Use the
[Mac build/install commands](macos-support.md#build-and-install-an-independent-app)
after writing the source. The plan itself does not create source, run a build,
install an App or certify delivery. Changing a
generated script invalidates that plan; preserve it and prepare a reviewed new
plan when the selected behavior needs to change.
