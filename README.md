## Convert EPP XSDs to JSON Schema

## Install & run

- checkout the code including submodules
- Install python and create virtual environment
- restore dependencies from requirements.txt
- run convert_epp_xsd_to_json_schema.py

## Generated schemas

The schemas are generated under `/output`

| Name  | Description  |
|---|---|
| rpp.json  | Main entrypoint contains custom RPP structures  |
| base.json | Core EPP protcol structures
| shared.json | Shared EPP structures
| epp-schema.json  | Merged schema containing all EPP structures

## Schema validation

Use the `rpp.json` schema to validate RPP documents, this includes integrated support for the EPP structures from the existing XSDs that have been converted.  

Use the individual schemas e.g. `domain.json` or `host.json` for testing limited to only those sub-schemas. 

## Generate server python

### Prerequisites
Install openapi-generator

### Run the generator
```
openapi-generator generate -g python-flask -i output/openapi_merged.yaml  -t ./templates/mustache/server/python-flask -o <path-to-client-repository>
```

## Generate client python

### Prerequisites
Install swagger-codegen

### Run the generator
```
swagger-codegen generate -l python -i output/openapi_merged.yaml -o <path-to-client-repository>
```

## VScode

Enable JSON validation using the generated schemas by modifying the project `.vscode/settings.json`. The example below validates all 
JSON files starting with `epp-` inside the `/test` folder against the `/output/rpp.json` schema.

```
{
    "json.schemas": [
        {
            "fileMatch": [
                "**/test/epp-*.json"
            ],
            "url": "./output/rpp.json"
        }
    ]
}
```

## Examples

See `/test` directory for more examples.

### Domain Create

```json
{
  "request": {
      "create": {
        "domain_create": {
          "name": "example.nl",
          "period": {"#value": 1, "@unit": "y"},
          "contact": [
            { "@type": "admin", "#value": "XXX-123"},
            { "@type": "tech", "#value": "XXX-123"},
            { "@type": "billing", "#value": "XXX-123"}
          ],
          "registrant": "XXX-999",
          "ns": { "hostObj": ["ns1.example.nl"]},
          "authInfo": {"pw": {"#value": "my-secret-token"}}
        }
      }
  }
}
```