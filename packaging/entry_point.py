"""PyInstaller entry point.

A plain top-level script (outside the flightgear_navdata_manager
package) that imports and runs the installed package's main(). Keeping
this separate from src/flightgear_navdata_manager/app.py avoids any
ambiguity in how PyInstaller resolves the package's own absolute
imports (e.g. "from flightgear_navdata_manager.application... import
...") -- this script relies purely on the package being properly
importable, exactly as it would be for any other consumer.
"""

import sys

from flightgear_navdata_manager.app import main

if __name__ == "__main__":
    sys.exit(main())
