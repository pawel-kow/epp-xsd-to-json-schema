## Convert EPP XSDs to JSON Schema

## Install & run

- checkout the code including submodules
- Install python and create virtual environment
- restore dependencies from requirements.txt
- run convert.py

## Generate server python

### Prerequisites
Install openapi-generator

### Run the generator
```
openapi-generator generate -g python-flask -i output/openapi_merged.yaml  -t ./mustache_templates/server/python-flask -o <path-to-client-repository>
```

## Generate client python

### Prerequisites
Install swagger-codegen

### Run the generator
```
swagger-codegen generate -l python -i output/openapi_merged.yaml -o <path-to-client-repository>
```