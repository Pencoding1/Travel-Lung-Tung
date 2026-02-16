import json

from pathlib import Path
from typing import Optional, List, Dict

from config.web_layout_constant.traveloka import JUNK, VEHICLES_LIST

JS_REMOVER_HELPER_PATH = Path(__file__).parent / "js_helper" / "xpath_remover.js"
JS_EXTRACTOR_HELPER_PATH = Path(__file__).parent / "js_helper" / "traveloka_vehicle_extractor.js"


def remover(xpath: Optional[List[str] | str | JUNK]=None, script: Optional[str]=None):
    if not script:
        if JS_REMOVER_HELPER_PATH.exists():
            script = JS_REMOVER_HELPER_PATH.read_text('utf-8')
        else:
            raise FileNotFoundError(f"Could not find JS helper at: {JS_REMOVER_HELPER_PATH}")
        
    if xpath:
        removal_commands = "\n".join([f"removeElement({json.dumps(xp)});" for xp in xpath])
    else:
        removal_commands = "\n".join([f"removeElement({json.dumps(xp.value)});" for xp in JUNK])

    return script.replace("{REMOVAL_LOGIC}", removal_commands)


def traveloka_vehicle_extractor(xpaths: Optional[Dict[str, str]]=None, script: Optional[str]=None):
    if not script:
        if JS_EXTRACTOR_HELPER_PATH.exists():
            script = JS_EXTRACTOR_HELPER_PATH.read_text('utf-8')
        else:
            raise FileNotFoundError(f"Could not find JS helper at: {JS_EXTRACTOR_HELPER_PATH}")
    
    if xpaths:
        script = script.replace("{js_paragraph}", json.dumps(xpaths.get('paragraphs')))
        script = script.replace("{js_buttons}", json.dumps(xpaths.get('button')))
        script = script.replace("{js_container}", json.dumps(xpaths.get('container')))
        script = script.replace("{wait_ms}", json.dumps(xpaths.get('wait_ms', 300)))

    else:
        script = script.replace("{js_paragraph}", json.dumps(VEHICLES_LIST.PARAGRAPH))
        script = script.replace("{js_buttons}", json.dumps((VEHICLES_LIST.BUTTON_LIST)))
        script = script.replace("{js_container}", json.dumps(VEHICLES_LIST.CONTAINER))
        script = script.replace("{wait_ms}", json.dumps(300))
    return script
