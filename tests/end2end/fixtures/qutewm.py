# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2016 Daniel Schadt
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

"""Fixtures for the qutewm window manager."""

import os
import sys

import pytest

from end2end.fixtures import testprocess


class QuteWMProcess(testprocess.Process):

    """Abstraction over a running qutewm instance."""

    SCRIPT = 'qutewm_sub'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wm_failed = False

    def _parse_line(self, line):
        self._log(line)
        if 'event loop started' in line:
            self.ready.emit()
        elif 'Another window manager is running, exiting' in line:
            self.wm_failed = True
            self.ready.emit()

    def _executable_args(self):
        if hasattr(sys, 'frozen'):
            executable = os.path.join(os.path.dirname(sys.executable),
                                      self.SCRIPT)
            args = []
        else:
            executable = sys.executable
            py_file = os.path.join(os.path.dirname(__file__),
                                   self.SCRIPT + '.py')
            args = [py_file]
        return executable, args

    def _default_args(self):
        return []


@pytest.yield_fixture(autouse=True)
def qutewm(request, qapp):
    """Fixture for a qutewm object which ensures clean setup/teardown.

    This does nothing if the test does not have the "qutewm" marker set.
    """
    if not request.node.get_marker('qutewm'):
        yield
        return
    if sys.platform != 'linux':
        pytest.skip('qutewm requires linux')
    qutewm = QuteWMProcess()
    qutewm.start()
    if qutewm.wm_failed:
        pytest.skip('another wm is running')
    yield qutewm
    qutewm.after_test()
    qutewm.terminate()
