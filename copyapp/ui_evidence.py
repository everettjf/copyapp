"""Conservative attribution of captured accessibility evidence."""

import re
from typing import Any, Dict


def ui_attribution(ui: Dict[str, Any], target_name: str) -> Dict[str, str]:
    """Identify only unambiguous system permission overlays; otherwise stay unsure."""
    captions = [str(item.get("caption") or "") for item in ui.get("elements", [])]
    for caption in captions:
        match = re.search(r'Allow [“"](.+?)[”"] to use your location\?', caption)
        if match:
            observed = match.group(1)
            return {"status": "system_permission_for_target" if observed == target_name
                    else "different_app_system_permission",
                    "observed_app_name": observed}
    return {"status": "unverified"}
