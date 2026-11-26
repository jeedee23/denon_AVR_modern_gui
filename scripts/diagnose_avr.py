"""Use the installed package's bounded diagnostic entrypoint."""

import sys

from denon_controller.app import main

raise SystemExit(main(["--diagnose", *sys.argv[1:]]))
