# This script extracts JSON schema back from the OpenAPI document

import yaml
import json
from yaml import Loader, Dumper

input_file = "swagger.yaml"
output_file = "reversed_schemas.json"

def change_paths(obj):
    if isinstance(obj, list):
        for x in obj:
            change_paths(x)
    elif isinstance(obj, dict):
        for l in obj:
            if l == "$ref":
                obj[l] = obj[l].replace("#/components/schemas/", "#/definitions/")
            else:
                change_paths(obj[l])

with open(input_file, "r") as f:
    openapi = yaml.load(f, Loader=Loader)

schemas_export = {
                    "$ref": "#/definitions/DomainCreateRequest",
                    "$schema": "http://json-schema.org/draft-07/schema#"
                 }
schemas_export["definitions"] = openapi["components"]["schemas"]
change_paths(schemas_export)
with open(output_file, "w") as f:
    json.dump(schemas_export, f, indent=2)
