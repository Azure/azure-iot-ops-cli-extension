# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import re
from typing import Dict, Optional

_ARMID_RE = re.compile(
    "(?i)/subscriptions/(?P<subscription>[^/]*)(/resourceGroups/(?P<resource_group>[^/]*))?"
    "(/providers/(?P<namespace>[^/]*)/(?P<type>[^/]*)/(?P<name>[^/]*)(?P<children>.*))?"
)

_CHILDREN_RE = re.compile(
    "(?i)(/providers/(?P<child_namespace>[^/]*))?/" "(?P<child_type>[^/]*)/(?P<child_name>[^/]*)"
)

_ARMNAME_RE = re.compile("^[^<>%&:\\?/]{1,260}$")


def parse_resource_id(rid: str) -> Dict[str, str]:
    """Parses a resource_id into its various parts.

    Returns a dictionary with a single key-value pair, 'name': rid, if invalid resource id.

    :param rid: The resource id being parsed
    :type rid: str
    :returns: A dictionary with with following key/value pairs (if found):

        - subscription:            Subscription id
        - resource_group:          Name of resource group
        - namespace:               Namespace for the resource provider (i.e. Microsoft.Compute)
        - type:                    Type of the root resource (i.e. virtualMachines)
        - name:                    Name of the root resource
        - child_namespace_{level}: Namespace for the child resoure of that level
        - child_type_{level}:      Type of the child resource of that level
        - child_name_{level}:      Name of the child resource of that level
        - last_child_num:          Level of the last child
        - resource_parent:         Computed parent in the following pattern: providers/{namespace}\
        /{parent}/{type}/{name}
        - resource_namespace:      Same as namespace. Note that this may be different than the \
        target resource's namespace.
        - resource_type:           Type of the target resource (not the parent)
        - resource_name:           Name of the target resource (not the parent)

    :rtype: dict[str,str]
    """
    if not rid:
        return {}
    match = _ARMID_RE.match(rid)
    if match:
        result = match.groupdict()
        children = _CHILDREN_RE.finditer(result["children"] or "")
        count = None
        for count, child in enumerate(children):
            result.update({key + "_%d" % (count + 1): group for key, group in child.groupdict().items()})
        result["last_child_num"] = count + 1 if isinstance(count, int) else None
        result = _populate_alternate_kwargs(result)
    else:
        result = {"name": rid}
    return {key: value for key, value in result.items() if value is not None}


def _populate_alternate_kwargs(kwargs) -> Dict[str, str]:
    """Translates the parsed arguments into a format used by generic ARM commands
    such as the resource and lock commands.
    """

    resource_namespace = kwargs["namespace"]
    resource_type = kwargs.get("child_type_{}".format(kwargs["last_child_num"])) or kwargs["type"]
    resource_name = kwargs.get("child_name_{}".format(kwargs["last_child_num"])) or kwargs["name"]

    _get_parents_from_parts(kwargs)
    kwargs["resource_namespace"] = resource_namespace
    kwargs["resource_type"] = resource_type
    kwargs["resource_name"] = resource_name
    return kwargs


def _get_parents_from_parts(kwargs) -> Dict[str, str]:
    """Get the parents given all the children parameters."""
    parent_builder = []
    if kwargs["last_child_num"] is not None:
        parent_builder.append("{type}/{name}/".format(**kwargs))
        for index in range(1, kwargs["last_child_num"]):
            child_namespace = kwargs.get("child_namespace_{}".format(index))
            if child_namespace is not None:
                parent_builder.append("providers/{}/".format(child_namespace))
            kwargs["child_parent_{}".format(index)] = "".join(parent_builder)
            parent_builder.append("{{child_type_{0}}}/{{child_name_{0}}}/".format(index).format(**kwargs))
        child_namespace = kwargs.get("child_namespace_{}".format(kwargs["last_child_num"]))
        if child_namespace is not None:
            parent_builder.append("providers/{}/".format(child_namespace))
        kwargs["child_parent_{}".format(kwargs["last_child_num"])] = "".join(parent_builder)
    kwargs["resource_parent"] = "".join(parent_builder) if kwargs["name"] else None
    return kwargs


def resource_id(**kwargs) -> str:
    """Create a valid resource id string from the given parts.

    This method builds the resource id from the left until the next required id parameter
    to be appended is not found. It then returns the built up id.

    :param dict kwargs: The keyword arguments that will make up the id.

        The method accepts the following keyword arguments:
            - subscription (required): Subscription id
            - resource_group:          Name of resource group
            - namespace:               Namespace for the resource provider (i.e. Microsoft.Compute)
            - type:                    Type of the resource (i.e. virtualMachines)
            - name:                    Name of the resource (or parent if child_name is also \
            specified)
            - child_namespace_{level}: Namespace for the child resoure of that level (optional)
            - child_type_{level}:      Type of the child resource of that level
            - child_name_{level}:      Name of the child resource of that level

    :returns: A resource id built from the given arguments.
    :rtype: str
    """
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    rid_builder = ["/subscriptions/{subscription}".format(**kwargs)]
    try:
        try:
            rid_builder.append("resourceGroups/{resource_group}".format(**kwargs))
        except KeyError:
            pass
        rid_builder.append("providers/{namespace}".format(**kwargs))
        rid_builder.append("{type}/{name}".format(**kwargs))
        count = 1
        while True:
            try:
                rid_builder.append("providers/{{child_namespace_{}}}".format(count).format(**kwargs))
            except KeyError:
                pass
            rid_builder.append("{{child_type_{0}}}/{{child_name_{0}}}".format(count).format(**kwargs))
            count += 1
    except KeyError:
        pass
    return "/".join(rid_builder)


def is_valid_resource_id(rid: str, exception_type: Optional[Exception] = None) -> bool:
    """Validates the given resource id."""

    is_valid = False
    try:
        is_valid = rid and resource_id(**parse_resource_id(rid)).lower() == rid.lower()
    except KeyError:
        pass
    if not is_valid and exception_type:
        raise exception_type()
    return is_valid


def is_valid_resource_name(rname: str, exception_type: Optional[Exception] = None) -> bool:
    """Validates the given resource name to ARM guidelines, individual services may be more restrictive."""

    match = _ARMNAME_RE.match(rname)

    if match:
        return True
    if exception_type:
        raise exception_type()
    return False
