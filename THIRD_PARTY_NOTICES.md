# Third-party notices

FlightGear NavData Manager's own source code is released under the MIT
License (see [LICENSE](LICENSE)). The third-party components below are
**not** covered by that license: each retains its own license, and nothing
in this project's MIT License changes or overrides those terms.

## Lucide icons — ISC License

The outline icons in
`src/flightgear_navdata_manager/presentation/theme/assets/icons/` are from
[Lucide](https://lucide.dev) (copied from the `lucide-static` package,
v0.469.0), used under the ISC License. Portions of Lucide are derived from
Feather (MIT). The full license text is included alongside the icons in
[`assets/icons/LICENSE`](src/flightgear_navdata_manager/presentation/theme/assets/icons/LICENSE)
and is shipped inside the packaged application.

## Qt and Qt for Python (PySide6, Shiboken6) — LGPLv3

The application's user interface is built with
[Qt for Python](https://doc.qt.io/qtforpython-6/) (PySide6 and Shiboken6),
which uses the Qt framework (Qt Core, Qt GUI, Qt Widgets, Qt SVG). Qt for
Python and these Qt modules are available under the GNU Lesser General
Public License version 3 (LGPLv3), among other licensing options; this
project uses them under the LGPLv3.

- This project's source code does not modify Qt or PySide6; it depends on
  the unmodified packages published on PyPI.
- The packaged macOS application (`FlightGear NavData Manager.app`)
  contains unmodified PySide6/Shiboken6 and Qt libraries as separate
  dynamic libraries and plugins (under `Contents/Frameworks/`), so they can
  be replaced with other compatible versions.
- License text: [GNU LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html)
  (which incorporates the [GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.html)).
- Qt licensing overview: <https://www.qt.io/licensing/> and
  <https://doc.qt.io/qt-6/licensing.html>
- Qt for Python licenses: <https://doc.qt.io/qtforpython-6/licenses.html>
- Source code for Qt and Qt for Python: <https://code.qt.io/> and
  <https://download.qt.io/official_releases/QtForPython/>.
  The release build was validated with PySide6 6.11.2.

Qt and PySide6 also contain third-party components of their own, listed
in their respective documentation.

## Python runtime and packaging (packaged app only)

The packaged application bundles a Python runtime (validated with Python
3.14), distributed under the
[Python Software Foundation License](https://docs.python.org/3/license.html),
including its standard library and the SQLite library it links to (SQLite
is in the [public domain](https://www.sqlite.org/copyright.html)). The
application is packaged with [PyInstaller](https://pyinstaller.org), whose
bootloader is distributed under the GPL with a special exception that
permits distributing applications built with it under any license (see
<https://pyinstaller.org/en/stable/license.html>).

## Aeronautical data (FAA and other sources)

The application does **not** include, download or redistribute any
navigation dataset. FAA aeronautical / National Airspace System (NAS)
data — such as the FAA's 28-day NASR subscription files — is publicly
available from the FAA and is obtained separately by each user; the app
only reads the files a user selects, and never copies or redistributes a
user's subscription files. Users are responsible for obtaining and using
any source data in accordance with the terms that apply to it.

The automated tests use small **synthetic** sample files in the FAA NASR
and FlightGear/X-Plane `.dat` formats (`tests/infrastructure/fixtures/`):
their identifiers, names and positions are fictional and do not describe
real facilities. They exist only to test the importers and are not part of
the packaged application.
