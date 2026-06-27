# -*- coding: utf-8 -*-
"""
StarDebate - Undo/Redo Coordinator (Singleton)
Manages QUndoStacks per panel, binds edit menu undo/redo to active panel.
"""
from PyQt5.QtWidgets import QUndoStack, QAction
from PyQt5.QtCore import QObject, pyqtSignal


class UndoCoordinator(QObject):
    _instance = None
    active_panel_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stacks = {}
        self._active_panel_id = None
        self._mw = None
        self._edit_menu = None
        self._current_undo_action = None
        self._current_redo_action = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self, main_window):
        self._mw = main_window
        self._edit_menu = self._find_edit_menu()
        self._install_placeholder_actions()

    def _find_edit_menu(self):
        if self._mw is None:
            return None
        top_nav_mgr = getattr(self._mw, '_top_nav_mgr', None)
        if top_nav_mgr is None:
            return None
        return top_nav_mgr.get_menu('edit_menu')

    def _install_placeholder_actions(self):
        if self._edit_menu is None:
            return
        undo_act = QAction('Undo', self._mw)
        undo_act.setEnabled(False)
        redo_act = QAction('Redo', self._mw)
        redo_act.setEnabled(False)
        self._current_undo_action = undo_act
        self._current_redo_action = redo_act
        actions = self._edit_menu.actions()
        before = actions[0] if actions else None
        self._edit_menu.insertAction(before, redo_act)
        self._edit_menu.insertAction(redo_act, undo_act)
        self._edit_menu.insertSeparator(redo_act)

    def _replace_menu_actions(self, stack):
        if self._edit_menu is None or stack is None:
            return
        self._remove_current_actions()
        undo_act = stack.createUndoAction(self._mw, 'Undo')
        redo_act = stack.createRedoAction(self._mw, 'Redo')
        actions = self._edit_menu.actions()
        before = actions[0] if actions else None
        self._edit_menu.insertAction(before, redo_act)
        self._edit_menu.insertAction(redo_act, undo_act)
        self._edit_menu.insertSeparator(redo_act)
        self._current_undo_action = undo_act
        self._current_redo_action = redo_act

    def _remove_current_actions(self):
        if self._edit_menu is None:
            return
        if self._current_undo_action:
            self._edit_menu.removeAction(self._current_undo_action)
            self._current_undo_action.deleteLater()
            self._current_undo_action = None
        if self._current_redo_action:
            self._edit_menu.removeAction(self._current_redo_action)
            self._current_redo_action.deleteLater()
            self._current_redo_action = None
        for act in self._edit_menu.actions():
            if act.isSeparator():
                self._edit_menu.removeAction(act)
                act.deleteLater()
                break

    def register_stack(self, panel_id, stack):
        self._stacks[panel_id] = stack
        if self._active_panel_id == panel_id:
            self._replace_menu_actions(stack)

    def unregister_stack(self, panel_id):
        self._stacks.pop(panel_id, None)
        if self._active_panel_id == panel_id:
            self._active_panel_id = None
            self._remove_current_actions()
            self._install_placeholder_actions()

    def get_stack(self, panel_id):
        return self._stacks.get(panel_id)

    def get_active_stack(self):
        if self._active_panel_id is None:
            return None
        return self._stacks.get(self._active_panel_id)

    def set_active_panel(self, panel_id):
        if self._active_panel_id == panel_id:
            return
        self._active_panel_id = panel_id
        self.active_panel_changed.emit(str(panel_id or ''))
        stack = self._stacks.get(panel_id) if panel_id else None
        if stack is not None:
            self._replace_menu_actions(stack)
        else:
            self._remove_current_actions()
            self._install_placeholder_actions()

    def register_plugin_stack(self, plugin_id, stack):
        self.register_stack('plugin_' + plugin_id, stack)

    def unregister_plugin_stack(self, plugin_id):
        self.unregister_stack('plugin_' + plugin_id)

    def set_active_plugin_panel(self, plugin_id):
        panel_id = 'plugin_' + plugin_id if plugin_id else None
        self.set_active_panel(panel_id)
