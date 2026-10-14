"""让 `python -m uediag` 生效的两行开关。"""

from uediag.cli import main

raise SystemExit(main())
