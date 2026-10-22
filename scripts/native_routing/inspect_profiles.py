import json
import os
import zipfile

root = os.environ.get("TVLT_ROOT", "/mnt/e/Project/TVLT_2026")
jar = os.path.join(root, ".runtime-native/graphhopper-11.1/download/graphhopper-web-11.1.jar")

with zipfile.ZipFile(jar) as z:
    for name in sorted(z.namelist()):
        if name.endswith(("foot.json", "car.json", "foot_elevation.json")):
            print("=== " + name + " ===")
            text = z.read(name).decode("utf-8")
            print(text)
            if name.endswith(".json"):
                try:
                    json.loads(text)
                    print("json_valid=yes")
                except Exception as e:
                    print("json_valid=no " + str(e))
            print()
