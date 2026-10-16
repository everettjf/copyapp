"""Template executed on Hopper's Python thread for one Copy APP function.

The launcher injects CONFIG below. Hopper's public Document/Procedure API is
used directly. REA's Hopper bridge informed the API selection (MIT license in
third-party/REA-LICENSE.txt); no REA module or service is loaded.
"""

import json
import hashlib
import os
import traceback


def _atomic_json(path, value):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.write("\n")
    os.replace(temporary, path)


def _run():
    target = os.path.realpath(CONFIG["target"])
    digest = hashlib.sha256()
    with open(target, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != CONFIG["slice_sha256"]:
        raise RuntimeError("Hopper target bytes differ from pinned Mach-O slice")
    matches = [document for document in Document.getAllDocuments()
               if document.getExecutableFilePath() and
               os.path.realpath(document.getExecutableFilePath()) == target]
    if len(matches) != 1:
        raise RuntimeError("Hopper did not uniquely open the requested binary")
    document = matches[0]
    try:
        if document.backgroundProcessActive():
            raise RuntimeError("Hopper analysis is still running")
        address = int(CONFIG["address"], 16)
        segment = document.getSegmentAtAddress(address)
        if segment is None:
            raise RuntimeError("requested address is outside Hopper segments")
        procedure = segment.getProcedureAtAddress(address)
        if procedure is None or procedure.getEntryPoint() != address:
            raise RuntimeError("Hopper did not resolve the exact function entry")
        name = segment.getNameAtAddress(address) or CONFIG["address"]
        pseudo = procedure.decompile()
        if not isinstance(pseudo, str) or not pseudo.strip():
            raise RuntimeError("Hopper returned no pseudocode")
        if len(pseudo.encode("utf-8")) > 2 * 1024 * 1024:
            raise RuntimeError("Hopper pseudocode exceeded limit")
        with open(CONFIG["pseudocode"], "w", encoding="utf-8") as stream:
            stream.write(pseudo)
        _atomic_json(CONFIG["result"], {
            "status": "complete", "address": "0x%x" % procedure.getEntryPoint(),
            "name": str(name), "signature": str(procedure.signatureString() or ""),
            "binary_path": target,
            "slice_sha256": digest.hexdigest(),
        })
    finally:
        document.closeDocument()


try:
    _run()
except Exception as error:
    _atomic_json(CONFIG["result"], {"status": "failed", "error": str(error)[:500],
                                    "traceback": traceback.format_exc()[-4000:]})
