def debug_print(obj, indent=0):
    prefix = " " * indent
    if isinstance(obj, dict):
        print(f"{prefix}{type(obj).__name__} {{")
        for k, v in obj.items():
            print(f"{prefix}  {k}:")
            debug_print(v, indent + 4)
        print(f"{prefix}}}")
    elif isinstance(obj, (list, tuple, set)):
        print(f"{prefix}{type(obj).__name__} [")
        for item in obj:
            debug_print(item, indent + 4)
        print(f"{prefix}]")
    elif hasattr(obj, "__dict__"):
        print(f"{prefix}{type(obj).__name__}(")
        for k, v in vars(obj).items():
            print(f"{prefix}  {k}:")
            debug_print(v, indent + 4)
        print(f"{prefix})")
    else:
        print(f"{prefix}{repr(obj)}")
