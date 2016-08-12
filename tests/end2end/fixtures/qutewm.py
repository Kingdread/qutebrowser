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

"""qutewm - a simple window manager for qutebrowser tests.

Usage:
    DISPLAY=:n python qutewm.py -- [options]

    Where n is the display you want to run qutewm on.

Available options:
    --help: Show this help.
    --debug: Show debugging information.
    --repl: Also start a repl in a separate thread (useful for debugging).

Available keybindings:
    Alt + F1 - cycle though all windows

Exit codes:
    42 - another window manager is running
"""

import sys
import logging

from Xlib.display import Display
from Xlib import X, XK, protocol, Xatom, Xutil


logging.basicConfig(
    style='{',
    format='{asctime} {name:10} {levelname:10} {module}:{funcName} {message}',
    level=logging.INFO,
)
log = logging.getLogger('qutewm')


class QuteWM:

    """Main class for the qutewm window manager.

    Attributes:
        dpy: The Display.
        dimensions: The screen's dimensions (width, height).
        windows: A list of all managed windows in mapping order.
        window_stack: A list of all windows in stack order.
        root: The root window.
        support_window: The window for the _NET_SUPPORTING_WM_CHECK.
    """

    WM_NAME = 'qutewm'

    ROOT_EVENT_MASK = X.SubstructureNotifyMask | X.SubstructureRedirectMask
    CLIENT_EVENT_MASK = X.StructureNotifyMask | X.PropertyChangeMask

    def __init__(self):
        log.info("initializing")
        self._handlers = {
            X.MapNotify: self.on_MapNotify,
            X.UnmapNotify: self.on_UnmapNotify,
            X.KeyPress: self.on_KeyPress,
            X.ClientMessage: self.on_ClientMessage,
            X.MapRequest: self.on_MapRequest,
            X.ConfigureRequest: self.on_ConfigureRequest,
            X.CirculateRequest: self.on_CirculateRequest,
            X.PropertyNotify: self.on_PropertyNotify,
        }
        self.dpy = Display()

        screen_width = self.dpy.screen().width_in_pixels
        screen_height = self.dpy.screen().height_in_pixels
        self.dimensions = (screen_width, screen_height)

        self._retcode = None
        self._needs_update = False
        self.root = self.dpy.screen().root
        self.support_window = None
        self.windows = []
        self.window_stack = []

        self.root.change_attributes(event_mask=self.ROOT_EVENT_MASK,
                                    onerror=self._wm_running)
        self.root.grab_key(
            self.dpy.keysym_to_keycode(XK.string_to_keysym("F1")),
            X.Mod1Mask, 1, X.GrabModeAsync, X.GrabModeAsync)

        self.ATOM_ACTIVE_WINDOW = self.dpy.get_atom('_NET_ACTIVE_WINDOW')
        self.ATOM_WM_STATE = self.dpy.get_atom('_NET_WM_STATE')
        # Used like atoms, but actually defined as constants
        self.ATOM_STATE_REMOVE = 0
        self.ATOM_STATE_ADD = 1
        self.ATOM_STATE_TOGGLE = 2
        self.ATOM_DEMANDS_ATTENTION = self.dpy.get_atom('_NET_WM_STATE_DEMANDS_ATTENTION')

        self._set_supported_attribute()
        self._set_supporting_wm_check()

    def _wm_running(self, error, request):
        """Called when another WM is already running."""
        log.error("Another window manager is running, exiting")
        # This is called async, which means we can't just raise an exception,
        # we need to signal the main thread to stop.
        self._retcode = 42

    def _set_supported_attribute(self):
        """Set the _NET_SUPPORTED attribute on the root window."""
        attributes = [
            '_NET_SUPPORTED',
            '_NET_ACTIVE_WINDOW',
            '_NET_CLIENT_LIST',
            '_NET_WM_STATE',
        ]
        self.root.change_property(
            self.dpy.get_atom('_NET_SUPPORTED'),
            Xatom.ATOM,
            32,
            [self.dpy.get_atom(x) for x in attributes],
        )


    def _set_supporting_wm_check(self):
        """Create and set a window for _NET_SUPPORTING_WM_CHECK."""
        self.support_window = self.root.create_window(
            0, 0, 10, 10, 0, self.dpy.screen().root_depth)

        for window in [self.root, self.support_window]:
            window.change_property(
                self.dpy.get_atom('_NET_SUPPORTING_WM_CHECK'),
                Xatom.WINDOW,
                32,
                [self.support_window.id],
            )
        self.support_window.change_property(
            self.dpy.get_atom('_NET_WM_NAME'),
            Xatom.STRING,
            8,
            self.WM_NAME,
        )

    def loop(self):
        """Start the X event loop.

        Return:
            The manager's exit code.
        """
        if self._retcode is not None:
            # avoid the "event loop started" message if we exit anyway
            return self._retcode
        log.info("event loop started")
        while 1:
            if self._retcode is not None:
                return self._retcode

            ev = self.root.display.next_event()
            log.debug("Got event {}".format(ev))
            handler = self._handlers.get(ev.type)
            if handler:
                handler(ev)

            self._update_clients()

    def activate(self, window):
        """Activate the given window, raise it and focus it."""
        log.debug("activating window {}".format(window))
        window.raise_window()
        window.set_input_focus(revert_to=X.RevertToNone, time=X.CurrentTime)
        self.root.change_property(
            self.dpy.get_atom('_NET_ACTIVE_WINDOW'),
            Xatom.WINDOW,
            32,
            [window.id] if window else [X.NONE],
        )
        # re-order window_stack so that the active window is at
        # window_stack[-1]
        try:
            index = self.window_stack.index(window)
        except ValueError:
            # Okay, fine then
            pass
        else:
            self.window_stack = (self.window_stack[index + 1:] +
                                 self.window_stack[:index + 1])

    def _update_clients(self):
        """Update _NET_CLIENT_LIST and _NET_ACTIVE_WINDOW attributes."""
        if not self._needs_update:
            return

        self.root.change_property(
            self.dpy.get_atom('_NET_CLIENT_LIST'),
            Xatom.WINDOW,
            32,
            [window.id for window in self.windows],
        )
        self.root.change_property(
            self.dpy.get_atom('_NET_ACTIVE_WINDOW'),
            Xatom.WINDOW,
            32,
            [self.window_stack[-1].id] if self.window_stack else [X.NONE],
        )
        self._needs_update = False

    def on_MapNotify(self, ev):
        """Called when a window is shown on screen ("mapped")."""
        width, height = self.dimensions
        ev.window.configure(x=0, y=0, width=width, height=height)
        log.debug("window created: {}".format(ev.window))
        ev.window.change_attributes(event_mask=self.CLIENT_EVENT_MASK)
        self.windows.append(ev.window)
        self.window_stack.append(ev.window)
        self._needs_update = True
        self.activate(ev.window)

    def on_MapRequest(self, ev):
        """Called when a MapRequest is intercepted."""
        ev.window.map()

    def on_ConfigureRequest(self, ev):
        """Called when a ConfigureRequest is intercepted."""
        ev.window.configure(x=ev.x, y=ev.y, width=ev.width, height=ev.height,
                            border_width=ev.border_width,
                            value_mask=ev.value_mask)

    def on_CirculateRequest(self, ev):
        """Called when a CirculateRequest is intercepted."""
        ev.window.circulate(ev.place)

    def on_UnmapNotify(self, ev):
        """Called when a window is unmapped from the screen."""
        log.debug("window destroyed: {}".format(ev.window))
        if ev.event == self.root and not ev.from_configure:
            log.debug("ignoring synthetic event")
            return
        try:
            self.windows.remove(ev.window)
            self.window_stack.remove(ev.window)
        except ValueError:
            log.debug("window was not in self.windows!")
        else:
            self._needs_update = True
        if self.window_stack:
            self.activate(self.window_stack[-1])

    def on_KeyPress(self, ev):
        """Called when a key that we're listening for is pressed."""
        # We only grabbed one key combination, so we don't need to check which
        # keys were actually pressed.
        if ev.child == X.NONE:
            return
        log.debug("cycling through available windows")
        if self.window_stack:
            self.activate(self.window_stack[0])

    def on_ClientMessage(self, ev):
        """Called when a ClientMessage is received."""
        if ev.client_type == self.ATOM_ACTIVE_WINDOW:
            log.info("external request to activate {}".format(ev.window))
            self.activate(ev.window)
        elif ev.client_type == self.ATOM_WM_STATE:
            self._handle_wm_state(ev)

    def on_PropertyNotify(self, ev):
        """Called when a PropertyNotify event is received."""
        if ev.atom == Xatom.WM_HINTS:
            hints = ev.window.get_wm_hints()
            if hints.flags & Xutil.UrgencyHint:
                log.info("urgency switch to {} (via WM_HINTS)"
                         .format(ev.window))
                self.activate(ev.window)

    def _handle_wm_state(self, ev):
        """Handle the _NET_WM_STATE client message."""
        client_properties = ev.window.get_property(self.ATOM_WM_STATE,
                                                   Xatom.ATOM, 0, 32)
        if client_properties is None:
            client_properties = set()
        else:
            client_properties = set(client_properties.value)

        action = ev.data[1][0]
        updates = {ev.data[1][1]}
        if ev.data[1][2] != 0:
            updates.add(ev.data[1][2])

        if action == self.ATOM_STATE_ADD:
            client_properties.update(updates)
        elif action == self.ATOM_STATE_REMOVE:
            client_properties.difference_update(updates)
        elif action == self.ATOM_STATE_TOGGLE:
            for atom in updates:
                if atom in client_properties:
                    client_properties.remove(atom)
                else:
                    client_properties.add(atom)
        else:
            log.error("unknown action: {}".format(action))

        log.debug("client properties for {}: {}".format(ev.window,
                                                        client_properties))
        ev.window.change_property(self.ATOM_WM_STATE, Xatom.ATOM, 32,
                                  client_properties)

        if self.ATOM_DEMANDS_ATTENTION in client_properties:
            log.info("urgency switch to {} (via _NET_WM_STATE)"
                     .format(ev.window))
            self.activate(ev.window)


def repl():
    import code
    code.interact(local=globals())


def main():
    if '--help' in sys.argv:
        print(__doc__)
        return

    if '--debug' in sys.argv:
        log.setLevel(logging.DEBUG)

    if '--repl' in sys.argv:
        import threading
        threading.Thread(target=repl).start()

    global wm
    wm = QuteWM()
    sys.exit(wm.loop())


if __name__ == '__main__':
    main()
