import yaml
import json
from yaml import Loader, Dumper

input_file_openapi = "output/openapi.yaml" 
input_file_schemas = "output/epp-schema.json"
output_file_openapi = "output/openapi_merged.yaml"

def change_paths(obj):
    if isinstance(obj, list):
        for x in obj:
            change_paths(x)
    elif isinstance(obj, dict):
        for l in obj:
            if l == "$ref":
                obj[l] = obj[l].replace("#/definitions/", "#/components/schemas/", ).replace("epp-schema.yaml", "").replace(":", "_")
            else:
                change_paths(obj[l])

with open(input_file_openapi, "r") as f:
    openapi = yaml.load(f, Loader=Loader)

with open(input_file_schemas, "r") as f:
    epp_schema = json.load(f)

openapi.setdefault("components", {}).setdefault("schemas", {})
openapi["components"]["schemas"].update(epp_schema["definitions"])
change_paths(openapi["components"]["schemas"])
with open(output_file_openapi, "w") as f:
    yaml.dump(openapi, f, Dumper=Dumper)
