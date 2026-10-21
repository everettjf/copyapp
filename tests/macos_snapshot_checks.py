"""Simulated snapshot controller; never manipulates a real VM disk or memory."""

import base64
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from copyapp.macos.case import canonical, digest
from copyapp.macos.chatcomputer import ChatComputerError, UnknownCompletion
from copyapp.macos.snapshots import snapshot_inventory, snapshot_operation
from copyapp.verify import verify_case


def make_snapshot_server(root: Path, vm: Path):
    buffer = io.BytesIO()
    Image.new("RGB", (16, 12), "blue").save(buffer, "PNG")
    script, log = root / "chatcomputer", root / "calls.jsonl"
    source = r'''import json,sys,os
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timezone
vm,log=Path(VM_PATH),Path(LOG_PATH)
root=vm/'Snapshots'
mode=os.environ.get('COPYAPP_TEST_SNAPSHOT_MODE','normal')
def state():
    p=root/'state.json'
    return json.loads(p.read_text()).get('currentID') if p.exists() else None
def capture(name,kind='manual',protected=False):
    parent=state(); ident=str(uuid4())
    row={'id':ident,'name':name,'kind':kind,'createdAt':datetime.now(timezone.utc).isoformat(),
         'isProtected':protected,'overlayCount':1,'hasThumbnail':False,'memoryBytes':4096}
    if parent: row['parentID']=parent
    folder=root/ident
    folder.mkdir(parents=True)
    (folder/'snapshot.json').write_text(json.dumps(row))
    (root/'state.json').write_text(json.dumps({'currentID':ident}))
    return ident
schemas={'move':{'x':{'type':'integer'},'y':{'type':'integer'}},'snapshot_take':{'name':{'type':'string'}},
         'snapshot_restore':{'snapshot':{'type':'string'},'save_current':{'type':'boolean'}}}
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request: continue
    method=request['method']
    if method=='initialize': result={'serverInfo':{'name':'chatcomputer','version':os.environ.get('COPYAPP_TEST_MCP_VERSION','0')}}
    elif method=='tools/list':
        result={'tools':[{'name':name,'inputSchema':{'type':'object','properties':schemas.get(name,{})}}
                         for name in ['status','screenshot','release','click','move','snapshot_take','snapshot_restore','snapshot_list']]}
        if mode=='schema-drift':
            next(row for row in result['tools'] if row['name']=='snapshot_restore')['inputSchema']['properties']['save_current']['type']='string'
    else:
        name,args=request['params']['name'],request['params']['arguments']
        with log.open('a') as out: out.write(json.dumps(request)+'\n')
        result={'isError':False,'content':[{'type':'text','text':'Simulated command completed'}]}
        if name=='screenshot': result['content'].append({'type':'image','mimeType':'image/png','data':IMAGE_BYTES})
        if name=='move' and mode=='human-takeover':
            result={'isError':True,'content':[{'type':'text','text':'User took over; wait for handback'}]}
        if name=='snapshot_take':
            if not root.exists(): capture('Simulated initial','initial',True)
            capture(args['name'])
            if mode=='lost-take': sys.exit(0)
        if name=='snapshot_restore':
            assert args['save_current'] is True
            if mode!='missing-safety': capture('Before restoring','safety')
            (root/'state.json').write_text(json.dumps({'currentID':args['snapshot']}))
            if mode=='lost-restore': sys.exit(0)
            if mode=='guest-not-ready': result={'isError':True,'content':[{'type':'text','text':'Snapshot committed but desktop readiness failed'}]}
        if name=='snapshot_list' and mode=='lost-list': sys.exit(0)
    print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
'''
    source = source.replace("VM_PATH", repr(str(vm))).replace("LOG_PATH", repr(str(log))).replace(
        "IMAGE_BYTES", repr(base64.b64encode(buffer.getvalue()).decode()))
    script.write_text("#!" + sys.executable + "\n" + source)
    script.chmod(0o755)
    return str(script), log


def exercise_snapshot_protocol(test, root: Path, environment: Path, vm: Path):
    # A real local collector checks reconnect/session binding. Only the public
    # snapshot metadata controller is simulated; no saved machine is restored.
    taken = snapshot_operation(environment, root / "snapshot-take", "take", timeout=5)
    test.assertTrue(verify_case(taken))
    restored = snapshot_operation(taken, root / "snapshot-restore", "restore", timeout=5)
    test.assertTrue(verify_case(restored))
    record = json.loads((restored / "snapshot-operation.json").read_text())
    test.assertNotEqual(record["before_session"], record["after_session"])
    test.assertFalse(record["shared_data_reset"])
    test.assertFalse(record["behavior_restoration_verified"])
    test.assertFalse(record["atomic_takeover_exclusion_verified"])
    test.assertEqual(record["safety_snapshot"]["kind"], "safety")
    log = root / "fake/calls.jsonl"

    def calls():
        return [json.loads(line)["params"]["name"] for line in log.read_text().splitlines()]

    for mode, action, source in (("lost-take", "take", environment), ("lost-restore", "restore", taken),
                                  ("guest-not-ready", "restore", taken)):
        before = calls().count("snapshot_" + action)
        failed = root / ("snapshot-" + mode)
        with patch.dict(os.environ, {"COPYAPP_TEST_SNAPSHOT_MODE": mode}):
            with test.assertRaises(UnknownCompletion):
                snapshot_operation(source, failed, action, timeout=5)
        test.assertEqual(calls().count("snapshot_" + action), before + 1)
        test.assertFalse(verify_case(failed))
        failure = json.loads((failed / "failure.json").read_text())
        test.assertTrue(failure["needs_inspection"])
        test.assertFalse(failure["action_retried"])
        test.assertTrue((failed / "failed-mcp.json").is_file())
        test.assertTrue((failed / "failure-catalog.json").is_file())
    inspected = snapshot_inventory(vm, root / "snapshot-after-uncertain")
    test.assertTrue(verify_case(inspected))
    before = calls().count("snapshot_take")
    with patch.dict(os.environ, {"COPYAPP_TEST_SNAPSHOT_MODE": "human-takeover"}):
        with test.assertRaises(ChatComputerError):
            snapshot_operation(environment, root / "snapshot-human-takeover", "take", timeout=5)
    test.assertEqual(calls().count("snapshot_take"), before)
    test.assertFalse(json.loads((root / "snapshot-human-takeover/failure.json").read_text())["action_submitted"])
    with patch.dict(os.environ, {"COPYAPP_TEST_SNAPSHOT_MODE": "missing-safety"}):
        with test.assertRaisesRegex(ValueError, "safety snapshot"):
            snapshot_operation(taken, root / "snapshot-no-safety", "restore", timeout=5)
    test.assertFalse(verify_case(root / "snapshot-no-safety"))
    before = calls().count("snapshot_restore")
    with patch.dict(os.environ, {"COPYAPP_TEST_SNAPSHOT_MODE": "schema-drift"}):
        with test.assertRaisesRegex(ValueError, "schema"):
            snapshot_operation(taken, root / "snapshot-schema-drift", "restore", timeout=5)
    test.assertEqual(calls().count("snapshot_restore"), before)
    target = json.loads((taken / "snapshot-operation.json").read_text())["snapshot"]
    live = vm / "Snapshots" / target["id"] / "snapshot.json"
    old = live.read_bytes()
    changed = json.loads(old); changed["name"] = "Changed by another actor"
    live.write_bytes(canonical(changed))
    try:
        with test.assertRaisesRegex(ValueError, "changed or is absent"):
            snapshot_operation(taken, root / "snapshot-target-drift", "restore", timeout=5)
        test.assertEqual(calls().count("snapshot_restore"), before)
        test.assertTrue(verify_case(taken))  # Historical verification is detached.
    finally: live.write_bytes(old)
    blocked = vm / "Snapshots/.restore"
    blocked.mkdir()
    try:
        before = calls().count("snapshot_take")
        with test.assertRaisesRegex(ValueError, "needs inspection"):
            snapshot_operation(environment, root / "snapshot-interrupted-journal", "take", timeout=5)
        test.assertEqual(calls().count("snapshot_take"), before)
    finally: blocked.rmdir()

    for relative, change in (("snapshot-operation.json", lambda value: value.update(shared_data_reset=True)),
                             ("snapshot-operation.json", lambda value: value.update(safety_snapshot=None)),
                             ("operation.json", lambda value: value["request"]["params"]["arguments"].update(save_current=False))):
        path, manifest_path = restored / relative, restored / "manifest.json"
        old, old_manifest = path.read_bytes(), manifest_path.read_bytes()
        value = json.loads(old); change(value); path.write_bytes(canonical(value))
        manifest = json.loads(old_manifest)
        for row in manifest["evidence"]:
            if row["path"] == relative: row["sha256"] = digest(path)
        manifest_path.write_bytes(canonical(manifest))
        try: test.assertFalse(verify_case(restored), relative)
        finally:
            path.write_bytes(old); manifest_path.write_bytes(old_manifest)
    test.assertTrue(verify_case(restored))
