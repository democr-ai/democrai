from __future__ import annotations

import json
import sys


def main() -> None:
    values = [str(item) for item in sys.argv[1:]]
    print(
        json.dumps(
            {
                "marker": "system_test_skill_script",
                "count": len(values),
                "values": values,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
