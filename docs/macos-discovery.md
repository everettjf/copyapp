# Discover representative Mac flows

Use this development workflow when a Mac analysis/rebuild request has no selected
flows. Work in the current coding-agent session with the registered ChatComputer
environment. The iOS discovery commands and USB identities do not apply.

Observe the exact acquired App with `mac observe --ax`, inspect screenshots and
structured AX, and explore relevant menus, shortcuts, document/file dialogs and
windows. Record visible capabilities, deferred/blocked behavior and unknowns.
Choose three to twelve distinct representative flows appropriate to the requested
scope. Do not interact with account/payment or unrelated data just to reach a count.

Write bounded Mac playbooks and run each once with `mac playbook --acquisition
<CASE> --script <JSON> --out <NEW_CASE>`. Inspect the saved evidence and verify
each case. Every accepted replay needs an explicit text, output-file or stopped
process assertion. A lost response or interrupted action requires state inspection;
`discover-check` does not replay or repair it. Renaming a script cannot make it a
second representative flow.

Write a discovery review JSON using the actual saved script hashes:

```json
{
  "schema_version": 2,
  "platform": "macos",
  "scope": "representative_flow_discovery",
  "reviewer": "current-agent",
  "selection_note": "Explain why these flows represent the requested scope.",
  "flows": [
    {
      "id": "edit-save",
      "source_script_sha256": "REPLACE_WITH_SAVED_PLAYBOOK_SHA256",
      "purpose": "Edit and save a new document.",
      "selection_reason": "Explain the observed capability exercised by this flow."
    }
  ],
  "capabilities": [
    {
      "id": "editing",
      "title": "Edit and save text",
      "flow_ids": ["edit-save"],
      "disposition": "available",
      "reason": "Describe the replay assertions and reviewed evidence."
    },
    {
      "id": "printing",
      "title": "Printing",
      "flow_ids": [],
      "disposition": "deferred",
      "reason": "Identified but outside the selected scope."
    }
  ],
  "inventory_note": "Describe how the known inventory was observed and its limits.",
  "unknowns": ["List unobserved behavior explicitly."]
}
```

The example shows the shape of one flow entry. Include entries for all three to
twelve actual replay cases; the command rejects the incomplete example. Capability
dispositions are `available`, `deferred` and `blocked`. Every flow must link to an
available capability; every available capability needs a flow. The reviewer owns
selection quality and inventory completeness.

```sh
.venv/bin/copyapp mac discover-check \
  --flow edit-save=cases/mac-edit-save \
  --flow reopen=cases/mac-reopen \
  --flow multiwindow=cases/mac-multiwindow \
  --review cases/mac-discovery-review.json --out cases/mac-discovery
.venv/bin/copyapp verify cases/mac-discovery
```

Acceptance verifies complete replay assertions, the exact original App path,
package and registered environment, script identity and inventory links. It saves
immutable child cases, the reviewed selection and `TASK.md` for behavior review.
Its status is input readiness; it certifies neither review truth, whole-App
coverage nor reconstruction. Separate-time observations remain separate-time.

Read the task and all linked raw evidence, then write the formal review described
in [the behavior review contract](macos-review.md). Use the accepted nested flows:

```sh
.venv/bin/copyapp mac report --discovery cases/mac-discovery \
  --review cases/mac-formal-review.json --out cases/mac-report
.venv/bin/copyapp verify cases/mac-report
```

The report preserves the discovery case and binds exactly its accepted replay
manifests. It requires all discovered capability IDs, including deferred/blocked
entries, to remain in the formal inventory. The formal review can add capabilities
and revise dispositions with reasons; the reviewer must carry unresolved unknowns
forward and inspect the meaning of any revisions. ID retention cannot prove that
two descriptions have the same semantics. Freeze the final known denominator and
explicit target with `mac rebuild-plan` before implementation.

For user-selected flows, the existing `mac report --flow ID=CASE` entry still
accepts one to twelve flows. Do not fabricate extra flows for a selected-flow job.
