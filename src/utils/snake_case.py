import re


def camel_to_snake(obj: dict) -> dict:
    """Functon to snake case a camel cased dict

    Args:
        obj (dict): Dict to be camel cased

    Returns:
        dict: Snake Cased dict
    """
    returned_dict = {}
    pattern = re.compile(r"(?<!^)(?=[A-Z])")
    for key, value in obj.items():
        name = pattern.sub("_", key).lower()
        returned_dict[name] = value

    return returned_dict
