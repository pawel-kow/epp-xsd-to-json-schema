from xmlschema import (
    XMLSchema,
    XsdElement
)
from xmlschema.validators import (
    XsdGroup,
    XsdAtomicBuiltin,
    XsdAnyElement,
    XsdComplexType,
    XsdAtomicRestriction
)

import jsonschema
import json
import os
import sys
import yaml
import logging
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

p = Path(__file__).parent / 'templates'
env = Environment(
    loader=FileSystemLoader(p))

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))

xsd_files = [
    { "file": "rfc5730_shared_structure.xsd", "label": "shared", "ns": "eppcom" },
    { "file": "rfc5730_base.xsd", "label": "base", "ns": "epp" },
    { "file": "rfc5731_domain_name_mapping.xsd", "label": "domain", "ns": "domain" },
    { "file": "rfc5732_host_mapping.xsd", "label": "host", "ns": "host" },
    { "file": "rfc5733_contact_mapping.xsd", "label": "contact", "ns": "contact" },
    { "file": "rfc5910_secdns.xsd", "label": "secDNS", "ns": "secDNS" }
]

# keep track of xsd that is currenly being processed
current_xsd = None

epp_commands = ['check', 'info', 'create', 'delete', 'update', 'transfer']
epp_response_data = ['chkData', 'infData', 'creData', 'panData', 'renData', 'trnData']

# keep list of extension commands
command_extensions = []
response_extensions = []

def lookupNS(ns):
    '''Return the XSD based on the provided namespace'''
    for xsd in xsd_files:
        if ns == xsd['ns']:
            return xsd
        
    return None

def convert_restrictions(t, schemadef):
    if hasattr(t, "min_value") and t.min_value is not None:
        schemadef["minimum"] = t.min_value
    if hasattr(t, "max_value") and t.max_value is not None:
        schemadef["maximum"] = t.max_value
    if hasattr(t, "min_length") and t.min_length is not None:
        schemadef["minLength"] = t.min_length
    if hasattr(t, "max_length") and t.max_length is not None:
        schemadef["maxLength"] = t.max_length
    if hasattr(t, "enumeration") and t.enumeration is not None:
        schemadef["enum"] = t.enumeration

def convert_simple_type(t, schemadef):
    if t.prefixed_name in ['xs:normalizedString', 'xs:string', 'xs:token', 'xs:language', 'xs:base64Binary']:
        schemadef["type"] = "string"
    elif t.prefixed_name in [
        'xs:unsignedShort', 'xs:integer', 'xs:int', 'xs:nonNegativeInteger',
        'xs:unsignedLong', 'xs:unsignedInt', 'xs:long', 'xs:unsignedByte']:
        schemadef["type"] = "integer"
        if t in ['xs:nonNegativeInteger', 'xs:unsignedLong', 'xs:unsignedInt', 'xs:unsignedByte']:
            schemadef["minimum"] = 0 if t.min_value is None or t.min_value < 0 else t.min_value
        if t in ['xs:unsignedByte']:
            schemadef["maximum"] = 255 if t.max_value is None or t.max_value > 255 else t.max_value
    elif t.prefixed_name in ['xs:hexBinary']:
        schemadef["type"] = "string"
        schemadef["pattern"] = '[0-9a-fA-F]+'
    elif t.prefixed_name in ['xs:decimal']:
        schemadef["type"] = "number"
    elif t.prefixed_name in ['xs:dateTime']:
        schemadef["type"] = "string"
        schemadef["format"] = "date-time"
    elif t.prefixed_name in ['xs:boolean']:
        schemadef["type"] = "boolean"
    elif t.prefixed_name in ['xs:date']:
        schemadef["type"] = "string"
        schemadef["format"] = "date"
    elif t.prefixed_name in ['xs:anyURI']:
        schemadef["type"] = "string"
        schemadef["format"] = "uri"
    elif t.prefixed_name in ['xs:duration']:
        schemadef["type"] = "string"
        schemadef["format"] = "duration"
    else:
        raise ValueError(f"No handling for simple type {t.prefixed_name} defined.")
    process_attributes(t, schemadef)

def convert_complex_type_content(t, schemadef):
    if isinstance(t, XsdGroup) and t.model == "choice":
        logging.debug("..choice")
        schemadef["oneOf"] = []
        for elem in t:
            if elem.local_name is not None:
                elemschemadef = {
                    "type": "object",
                    "properties": {
                        elem.local_name:  {
                        }
                    }
                }
                convert_complex_type_content(elem, elemschemadef["properties"][elem.local_name])
                process_cardinality(elem, elemschemadef, elem.local_name)
            else:
                convert_complex_type_content(elem, elemschemadef)
            schemadef["oneOf"] += [elemschemadef]
        if t.mixed:
            logging.error(f"ERROR: Unhandled complex choice type with mixed content: {t}")
            exit(1)
    elif isinstance(t, XsdGroup) and t.model == "sequence":
        logging.debug("..sequence")
        objschema = {
            "type": "object",
            "properties": {}
        }
        anyofs = []
        additional_props = []
        additional_props_min_cnt = 0
        additional_props_max_cnt = 0
        for elem in t:
            subelem = {}
            convert_complex_type_content(elem, subelem)
            if 'anyOf' in subelem:
                anyofs += [subelem['anyOf']]
            elif elem.local_name is not None:
                objschema["properties"][elem.local_name] = subelem
                #process_attributes(elem, objschema)
                process_cardinality(elem, objschema, elem.local_name)
            else:
                additional_props += [subelem]
                if additional_props_max_cnt is not None:
                    if elem.effective_max_occurs is None:
                        additional_props_max_cnt = None
                    else:
                        additional_props_max_cnt += elem.effective_max_occurs
                additional_props_min_cnt += elem.effective_min_occurs
        if len(additional_props) > 0:
            schemadef.update({
                "allOf": [
                    objschema
                ] + additional_props
            })
        logging.debug(f"AddProps {t} {schemadef} {additional_props}")
        #if len(additional_props) > 0:
        # if len(additional_props) == 1:
        #     objschema.update({
        #         "additionalProperties": additional_props[0],
        #         "minProperties": additional_props_min_cnt
        #     })
        # elif len(additional_props) > 1:
        #     objschema.update({
        #         "additionalProperties": {
        #             "anyOf": additional_props
        #         },
        #         "minProperties": additional_props_min_cnt
        #     })
        # if len(additional_props) > 0 and additional_props_max_cnt is not None:
        #     objschema.update({
        #         "maxProperties": additional_props_max_cnt
        #     })
        if len(anyofs) > 0:
            schemadef.update({
                "anyOf": [
                    objschema
                ] + anyofs
            })
        else:
            schemadef.update(objschema)
        if t.parent.mixed:
            schemadef["properties"]["#text"] = {
                "type": "array",
                "items": {
                    "type": "string"
                }
            }
    else:
        convert_any_type(t, schemadef)

def convert_to_array(t, schemadef, prop_local_name):
    schemadef["properties"][prop_local_name] = {
        "type": "array",
        "items": schemadef["properties"][prop_local_name]
    }
    if t.effective_max_occurs is not None:
        schemadef["properties"][prop_local_name]["maxItems"] = t.effective_max_occurs
    if t.effective_min_occurs is not None:
        schemadef["properties"][prop_local_name]["minItems"] = t.effective_min_occurs
    if t.effective_min_occurs is not None and t.effective_min_occurs > 0:
        schemadef.setdefault("required", [])
        schemadef["required"] += [prop_local_name]

def process_cardinality(t, schemadef, prop_local_name):
    if t.effective_max_occurs is not None:
        if t.effective_max_occurs == 1:
            if t.effective_min_occurs == 1:
                schemadef.setdefault("required", [])
                schemadef["required"] += [t.local_name]
                return schemadef
        else:
            convert_to_array(t, schemadef, prop_local_name)
    else:
        convert_to_array(t, schemadef, prop_local_name)

def process_attributes(t, schemadef):
    if hasattr(t, "attributes") and t.attributes:
        for a in t.attributes:
            if a is not None:
                if t.attributes[a].type is not None:
                    attrschema = {}
                    convert_any_type(t.attributes[a].type, attrschema)
                    if "properties" in schemadef:
                        schemadef["properties"][f"@{t.attributes[a].name}"] = attrschema
                    elif "type" in schemadef or "$ref" in schemadef:
                        olddef = {}
                        olddef.update(schemadef)
                        for x in [k for k in schemadef.keys()]:
                            del schemadef[x]
                        schemadef["properties"] = {}
                        schemadef["properties"][f"@{t.attributes[a].name}"] = attrschema
                        schemadef["properties"]["#value"] = olddef
                        schemadef["type"] = "object"
                    else:
                        raise ValueError(f"Attribute {a} cannot be processed")
                else:
                    raise ValueError(f"Attribute {a} without type")

def create_ref(display_name):
    '''Create a valid reference to an internal or external schema'''
    schema_file = lookupNS(display_name.split(':')[0])
    logging.debug(f'Found file for namespace: {schema_file}')
    
    ref_start = '#'
    if schema_file and schema_file['ns'] != current_xsd['ns']:
        # only use ref to external schema when its not the current scheme
        ref_start = f'{schema_file["label"]}.json#'

    return f'{ref_start}/$defs/{display_name.replace(":", "_")}'

def convert_any_type(t, schemadef):
    # first process the base type
    if hasattr(t, "base_type") and t.base_type is not None:
        convert_any_type(t.base_type, schemadef)
    # now process elements with type specified
    if isinstance(t, XsdElement) and hasattr(t, "type") and isinstance(t.type, XsdComplexType) \
        and t.type.name == '{http://www.w3.org/2001/XMLSchema}anyType':
        logging.debug("..anyType")
        schemadef.update({
             "type": "boolean",
             "default": False
         })
    elif isinstance(t, XsdElement) and hasattr(t, "type"):
        # handling for built-ins
        if isinstance(t.type, XsdAtomicBuiltin):
            logging.debug(f"..builtInType {t.type.prefixed_name}")
            convert_simple_type(t.type, schemadef)
            process_attributes(t.type, schemadef)
        # handling for special type "anyType"
        elif isinstance(t.type, XsdComplexType) and t.type.qualified_name == '{http://www.w3.org/2001/XMLSchema}anyType':
            logging.debug(f"..any type")
            schemadef.update({
                "type": "object"
            })
        # if it is not built-in and not "anyType" then this is a reference
        else:
            logging.debug(f"Include reference for {t.type.display_name}")

            new_ref = create_ref(t.type.display_name)
            schemadef.update({
                "$ref": new_ref
            })
    # processing for complex types
    elif isinstance(t, XsdComplexType):
        convert_complex_type_content(t.content, schemadef)
        process_attributes(t, schemadef)
    # handling for direct built-ins
    elif isinstance(t, XsdAtomicBuiltin):
        convert_simple_type(t, schemadef)
        process_attributes(t, schemadef)
    # handling for restrictions
    elif isinstance(t, XsdAtomicRestriction):
        convert_restrictions(t, schemadef)
        process_attributes(t, schemadef)
    # handling for direct anyType
    elif isinstance(t, XsdAnyElement):
        schemadef.update({
            "type": "object"
        })
    else:
        if schemadef == {}:
            raise ValueError(f"No handling for type {t} defined")
        else:
            process_attributes(t, schemadef)

    return schemadef

def convert_simple_types(xsd, json_schema):
    # Iterate through the XSD simple types
    for t in xsd.simple_types:
        schemadef = convert_any_type(t, {})

        name = t.display_name.replace(":", "_")
        json_schema['$defs'][name] = schemadef

def convert_root_element(e):
    '''Create schema structures for XSD root elements'''
    new_ref = create_ref(e.type.display_name)
    name = e.display_name.replace(":", '_')

    json_schema = {
       "type": "object",
       "properties": {
           name: {
            "$ref": new_ref
           },
       },
       "required": [name] 
    }
    
    ext_name =  e.display_name.split(':')[1]
    if ext_name in epp_commands:
        command_extensions.append(json_schema)
    elif ext_name in epp_response_data:
        response_extensions.append(json_schema)

    return json_schema

def convert_root_elements(xsd, json_schema):
    # get name of the root element, these are command or response extensions
    # and are added to the final schema, but at the root of the schema
    # not under $defs
    json_schema['anyOf'] = []
    for e in xsd.root_elements:
        logging.debug(f'Found root element: {e}, name: {e.display_name} of type {e.type}')
        schemadef = convert_root_element(e)
        json_schema['anyOf'].append(schemadef)

def convert_complex_types(xsd, json_schema):
    # Iterate through the XSD complex types
    for t in xsd.complex_types:
        logging.debug(f'display name: {t.display_name}')
        schemadef = convert_any_type(t, {})

        name = t.display_name.replace(":", "_")
        json_schema['$defs'][name] = schemadef


def xsd_to_json_schema(xsd_file):
    # Load the XSD file using xmlschema
    xsd = XMLSchema(f'xsd/{xsd_file}')

    # Create a JSON schema dictionary
    json_schema = new_schema()

    convert_simple_types(xsd, json_schema)
    convert_complex_types(xsd, json_schema)
    convert_root_elements(xsd, json_schema)

    try:
        jsonschema.Draft202012Validator(json_schema)
    except Exception as e:
        logging.error(f"Converting {xsd_file} resulted in an invalid schema: {e}")
        exit(1)

    return json_schema

def dump_file(data, path, name, json_format=True):
    if not os.path.exists(path):
        os.makedirs(path)
    
    with open(f'{path}/{name}', 'w') as f:
        if json_format:
           json.dump(data, f, indent=2)
        else:
           yaml.dump(json_schema, f)

def merge_schemas(schema1, schema2):
    for k, v in schema2['$defs'].items():
       schema1['$defs'][k] = v

def new_schema():
    return {
            "type": "object",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "unevaluatedProperties": False,
            "$defs": {}
        }

def update_ref(obj):
    if type(obj) is list:
        for item in obj:
            update_ref(item)
    elif type(obj) is dict:
        for k,v in obj.items():
            if '$ref' == (k) and 'json#/' in v:
                ref_new = v.split('.json',1)[1]
                logging.debug(f'Update external reference {v} -> {ref_new}')
                obj[k] = ref_new
            else:
               update_ref(v)
    
        
def update_refs(json_schema):
    '''Update the reference, replace the external reference to an internal reference'''
    for definition in json_schema['$defs']:
        update_ref( json_schema['$defs'][definition])

def update_extensions(json_schema):
    updated_command_extensions = {
      "oneOf": []
    }

    updated_response_extensions = {
      "oneOf": []
    }

    for ext in command_extensions:
        logging.debug(f'Found extension: {ext}')
        updated_command_extensions['oneOf'].append(ext)

    for ext in response_extensions:
        logging.debug(f'Found extension: {ext}')
        updated_response_extensions['oneOf'].append(ext)


    logging.debug(f"updated_command_extensions: {updated_command_extensions}")
    logging.debug(f"updated_response_extensions: {updated_response_extensions}")

    # add the found extensions to the final schema, replacing the "anything is accepted here"
    # extion with actual allowed data structures
    json_schema['$defs']['epp_readWriteType'] = updated_command_extensions
    json_schema['$defs']['epp_extAnyType'] = updated_response_extensions

if __name__ == "__main__":

    json_schema = new_schema()
    
    for xsd in xsd_files:
        current_xsd = xsd
        logging.info(f'Start processing file {xsd["file"]}')
        # create new json schema file for each xsd, include
        # external references to other json schemas so each 
        # generated schema contains only the tyopes declared in the converted xsd
        new_json_schema = xsd_to_json_schema(xsd['file'])
        dump_file(new_json_schema, 'output', f'{xsd["label"]}.json')
        merge_schemas(json_schema, new_json_schema)
    
    logging.info(f'Update merged EPP schema')
    # the individual generated schema may contain external references, to keep schemas small 
    # make debugging easier.
    # for the final merged schema change all external references to local references
    update_refs(json_schema)
    # add the detected command and response extensions from the object mapping xsd to the epp_readWriteType
    update_extensions(json_schema)

    dump_file(json_schema, 'output', 'epp-schema.json')
    dump_file(json_schema, 'output', 'epp-schema.yaml', False)

    # create entrypoint schema, contains the rpp specific structures
    logging.info(f'Create RPP schema')
    rpp = env.get_template('./json-schema/rpp-template.json.j2').render(epp_schema_file='epp-schema.json')
    dump_file(json.loads(rpp), 'output', 'rpp.json')



    