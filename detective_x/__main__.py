"""Entry point: python -m detective_x"""

from __future__ import annotations

import sys

from .cli import parse_args
from .exceptions import DetectiveXError
from .persistence.save_manager import FileStorage
from .ui import colours as C
from .ui.terminal import TerminalGame


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.storage = FileStorage(args.save)
    try:
        game = TerminalGame(args)
        if args.case:
            case = next((c for c in game.cases if c.id == args.case), None)
            if case is None:
                print(f"No case number {args.case}.")
                return 2
            game.brief_and_play(case)
            return 0
        return game.run()
    except DetectiveXError as exc:
        print(C.paint(f"\n  {exc}\n", C.RED))
        return 1
    except KeyboardInterrupt:
        print("\n  Interrupted. Progress since your last save was not kept.\n")
        return 130


if __name__ == "__main__":
    sys.exit(main())
