# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2015 Daniel Schadt
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""pdf.js integration for qutebrowser."""

import os
import hashlib
import urllib.parse

from PyQt5.QtCore import QUrl

from qutebrowser.utils import utils, javascript, usertypes, log


_files = {}


class FileContainer:
    __slots__ = ('data', 'count')

    def __init__(self, data):
        self.data = data
        self.count = 1

    def __repr__(self):
        ident = hashlib.sha256(self.data).hexdigest()
        return utils.get_repr(self, data='{'+ident+'}', count=self.count)


class PDFJSNotFound(Exception):

    """Raised when no pdf.js installation is found.

    Attributes:
        path: path of the file that was requested but not found.
    """

    def __init__(self, path):
        self.path = path
        message = "Path '{}' not found".format(path)
        super().__init__(message)


def is_pdfjs_viewer(url: QUrl) -> bool:
    """Checks whether the given URL belongs to the pdf.js viewer."""
    return get_pdf_url(url) is not None


def get_pdf_url(url: QUrl) -> QUrl:
    """Extracts the original file url from a pdf.js viewer url."""
    query = urllib.parse.parse_qs(url.query())
    return query.get('origin')


def show_pdfjs(openurl, url, data, basename):
    log.pdfjs.debug("showing {}".format(url))
    ident = add_file(data)
    # Append the basename after the hash so that the viewer has a nicer title
    # (the filename instead of the hash)
    file_url = 'qute://pdfjs/data/{}/{}'.format(ident, basename)
    view_url = QUrl('qute://pdfjs/web/viewer.html?file={}&origin={}'.format(
        urllib.parse.quote_plus(file_url),
        urllib.parse.quote_plus(url.toString()),
    ))
    openurl(view_url)


def add_file(data):
    ident = hashlib.sha256(data).hexdigest()
    if ident in _files:
        _files[ident].count += 1
    else:
        _files[ident] = FileContainer(data)
    log.pdfjs.debug("added file: {}".format(_files[ident]))
    return ident


def get_file(ident):
    container = _files[ident]
    container.count -= 1
    log.pdfjs.debug("retrieved file: {}".format(container))
    if container.count == 0:
        del _files[ident]
    return container.data


SYSTEM_PDFJS_PATHS = [
    # Debian pdf.js-common
    # Arch Linux pdfjs (AUR)
    '/usr/share/pdf.js/',
    # Arch Linux pdf.js (AUR)
    '/usr/share/javascript/pdf.js/',
    # Debian libjs-pdf
    '/usr/share/javascript/pdf/',
    # fallback
    os.path.expanduser('~/.local/share/qutebrowser/pdfjs/'),
]


def get_pdfjs_res_and_path(path):
    """Get a pdf.js resource in binary format.

    Returns a (content, path) tuple, where content is the file content and path
    is the path where the file was found. If path is None, the bundled version
    was used.

    Args:
        path: The path inside the pdfjs directory.
    """
    path = path.lstrip('/')
    content = None
    file_path = None

    # First try a system wide installation
    # System installations might strip off the 'build/' or 'web/' prefixes.
    # qute expects them, so we need to adjust for it.
    names_to_try = [path, _remove_prefix(path)]
    for system_path in SYSTEM_PDFJS_PATHS:
        content, file_path = _read_from_system(system_path, names_to_try)
        if content is not None:
            break

    # Fallback to bundled pdf.js
    if content is None:
        res_path = '3rdparty/pdfjs/{}'.format(path)
        try:
            content = utils.read_file(res_path, binary=True)
        except FileNotFoundError:
            raise PDFJSNotFound(path) from None

    return (content, file_path)


def get_pdfjs_res(path):
    """Get a pdf.js resource in binary format.

    Args:
        path: The path inside the pdfjs directory.
    """
    content, _path = get_pdfjs_res_and_path(path)
    return content


def _remove_prefix(path):
    """Remove the web/ or build/ prefix of a pdfjs-file-path.

    Args:
        path: Path as string where the prefix should be stripped off.
    """
    prefixes = {'web/', 'build/'}
    if any(path.startswith(prefix) for prefix in prefixes):
        return path.split('/', maxsplit=1)[1]
    # Return the unchanged path if no prefix is found
    return path


def _read_from_system(system_path, names):
    """Try to read a file with one of the given names in system_path.

    Returns a (content, path) tuple, where the path is the filepath that was
    used.

    Each file in names is considered equal, the first file that is found
    is read and its binary content returned.

    Returns (None, None) if no file could be found

    Args:
        system_path: The folder where the file should be searched.
        names: List of possible file names.
    """
    for name in names:
        try:
            full_path = os.path.join(system_path, name)
            with open(full_path, 'rb') as f:
                return (f.read(), full_path)
        except OSError:
            continue
    return (None, None)


def is_available():
    """Return true if a pdfjs installation is available."""
    try:
        get_pdfjs_res('build/pdf.js')
    except PDFJSNotFound:
        return False
    else:
        return True
