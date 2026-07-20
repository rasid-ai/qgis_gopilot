"""Qt5/Qt6 Compatibility Layer for QGIS 3.x and 4.x

This module provides version-safe Qt constants that work across both:
- QGIS 3.x (Qt5/PyQt5) - uses flat enum syntax: Qt.AlignCenter, QFrame.HLine
- QGIS 4.x (Qt6/PyQt6) - uses scoped enum syntax: Qt.AlignmentFlag.AlignCenter, QFrame.Shape.HLine

WHY THIS FILE EXISTS
====================
In Qt6, all enum constants were moved under their enum class names (scoped enums).
Code that worked in Qt5 breaks in Qt6 with AttributeError.

Example:
    Qt5: Qt.AlignCenter, Qt.WindowMinimizeButtonHint
    Qt6: Qt.AlignmentFlag.AlignCenter, Qt.WindowType.WindowMinimizeButtonHint

Direct usage of Qt.AlignCenter fails on QGIS 4.x (Qt6) with:
    AttributeError: type object 'Qt' has no attribute 'AlignCenter'

HOW THIS WORKS
==============
1. Detect Qt version at runtime using QT_VERSION
2. Export version-safe constants with Qt_ prefix
3. All plugin code imports from this file instead of using raw Qt.* constants

Example usage in your code:
    from .compat import Qt_AlignCenter, Qt_WindowMinimizeButtonHint

    label.setAlignment(Qt_AlignCenter)  # Works on both Qt5 and Qt6
    self.setWindowFlags(self.windowFlags() | Qt_WindowMinimizeButtonHint)

SUPPORTED VERSIONS
==================
This compatibility layer enables the plugin to run on:
- QGIS 3.0 - 3.99 (Qt5)
- QGIS 4.0 - 4.99 (Qt6)

As specified in metadata.txt:
    qgisMinimumVersion=3.0
    qgisMaximumVersion=4.99

IMPORTANT RULES
===============
1. ALWAYS use qgis.PyQt imports, NEVER PyQt5 or PyQt6 directly
2. NEVER use raw Qt.Something constants outside this file
3. If you need a new Qt constant, add it to BOTH the QT6 and else branches here
4. Use Qt6 scoped enum syntax (Qt.EnumClass.Value) in the QT6 branch
5. Use Qt5 flat syntax (Qt.Value) in the else branch

ADDING NEW CONSTANTS
====================
If you get AttributeError for a missing Qt constant on QGIS 4:

1. Find the Qt6 enum class name (e.g., AlignmentFlag, WindowType, CursorShape)
2. Add to QT6 branch:
   Qt_ConstantName = Qt.EnumClass.ConstantName

3. Add to Qt5 branch (else):
   Qt_ConstantName = Qt.ConstantName

4. Import in your file:
   from .compat import Qt_ConstantName
"""
from qgis.PyQt.QtCore import QT_VERSION, Qt
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtWidgets import QFrame, QLineEdit, QMessageBox, QDialog, QSizePolicy

QT6 = QT_VERSION >= 0x060000


def exec_dialog(dialog):
    """Execute a dialog in a Qt5/Qt6 compatible way.

    Qt5 uses exec_(), Qt6 uses exec().
    This wrapper handles both versions.

    Usage:
        from .compat import exec_dialog
        result = exec_dialog(my_dialog)
    """
    if QT6:
        return dialog.exec()
    else:
        return dialog.exec_()

if QT6:
    # Window flags
    Qt_Window                    = Qt.WindowType.Window
    Qt_Dialog                    = Qt.WindowType.Dialog
    Qt_WindowMinimizeButtonHint  = Qt.WindowType.WindowMinimizeButtonHint
    Qt_WindowMaximizeButtonHint  = Qt.WindowType.WindowMaximizeButtonHint
    Qt_WindowCloseButtonHint     = Qt.WindowType.WindowCloseButtonHint
    Qt_WindowStaysOnTopHint      = Qt.WindowType.WindowStaysOnTopHint

    # Alignment
    Qt_AlignCenter               = Qt.AlignmentFlag.AlignCenter
    Qt_AlignLeft                 = Qt.AlignmentFlag.AlignLeft
    Qt_AlignRight                = Qt.AlignmentFlag.AlignRight
    Qt_AlignTop                  = Qt.AlignmentFlag.AlignTop
    Qt_AlignBottom               = Qt.AlignmentFlag.AlignBottom
    Qt_AlignVCenter              = Qt.AlignmentFlag.AlignVCenter
    Qt_AlignHCenter              = Qt.AlignmentFlag.AlignHCenter

    # Orientation
    Qt_Horizontal                = Qt.Orientation.Horizontal
    Qt_Vertical                  = Qt.Orientation.Vertical

    # Item roles / flags
    Qt_UserRole                  = Qt.ItemDataRole.UserRole
    Qt_DisplayRole               = Qt.ItemDataRole.DisplayRole
    Qt_CheckStateRole            = Qt.ItemDataRole.CheckStateRole
    Qt_ItemIsEditable            = Qt.ItemFlag.ItemIsEditable
    Qt_ItemIsEnabled             = Qt.ItemFlag.ItemIsEnabled
    Qt_ItemIsSelectable          = Qt.ItemFlag.ItemIsSelectable

    # Mouse buttons
    Qt_LeftButton                = Qt.MouseButton.LeftButton
    Qt_RightButton               = Qt.MouseButton.RightButton
    Qt_MiddleButton              = Qt.MouseButton.MiddleButton

    # QFrame shapes
    QFrame_NoFrame               = QFrame.Shape.NoFrame
    QFrame_HLine                 = QFrame.Shape.HLine
    QFrame_VLine                 = QFrame.Shape.VLine
    QFrame_StyledPanel           = QFrame.Shape.StyledPanel
    QFrame_Panel                 = QFrame.Shape.Panel
    QFrame_Box                   = QFrame.Shape.Box

    # QLineEdit echo modes
    QLineEdit_Normal             = QLineEdit.EchoMode.Normal
    QLineEdit_Password           = QLineEdit.EchoMode.Password
    QLineEdit_NoEcho             = QLineEdit.EchoMode.NoEcho
    QLineEdit_PasswordEchoOnEdit = QLineEdit.EchoMode.PasswordEchoOnEdit

    # QPainter render hints
    QPainter_Antialiasing        = QPainter.RenderHint.Antialiasing
    QPainter_TextAntialiasing    = QPainter.RenderHint.TextAntialiasing
    QPainter_SmoothPixmapTransform = QPainter.RenderHint.SmoothPixmapTransform

    # QMessageBox
    QMessageBox_Information      = QMessageBox.Icon.Information
    QMessageBox_Question         = QMessageBox.Icon.Question
    QMessageBox_Warning          = QMessageBox.Icon.Warning
    QMessageBox_Critical         = QMessageBox.Icon.Critical
    QMessageBox_Yes              = QMessageBox.StandardButton.Yes
    QMessageBox_No               = QMessageBox.StandardButton.No
    QMessageBox_Ok               = QMessageBox.StandardButton.Ok
    QMessageBox_Cancel           = QMessageBox.StandardButton.Cancel

    # QDialog
    QDialog_Accepted             = QDialog.DialogCode.Accepted
    QDialog_Rejected             = QDialog.DialogCode.Rejected

    # Window types / widget attributes
    Qt_Tool                      = Qt.WindowType.Tool
    Qt_FramelessWindowHint       = Qt.WindowType.FramelessWindowHint
    Qt_WA_TranslucentBackground  = Qt.WidgetAttribute.WA_TranslucentBackground

    # Pen styles
    Qt_SolidLine                 = Qt.PenStyle.SolidLine

    # Keyboard keys
    Qt_Key_Escape                = Qt.Key.Key_Escape
    Qt_Key_Backspace             = Qt.Key.Key_Backspace
    Qt_Key_Delete                = Qt.Key.Key_Delete
    Qt_Key_Return                = Qt.Key.Key_Return
    Qt_Key_Enter                 = Qt.Key.Key_Enter

    # QSizePolicy
    QSizePolicy_Expanding        = QSizePolicy.Policy.Expanding
    QSizePolicy_Preferred        = QSizePolicy.Policy.Preferred
    QSizePolicy_Fixed            = QSizePolicy.Policy.Fixed
    QSizePolicy_Minimum          = QSizePolicy.Policy.Minimum
    QSizePolicy_Maximum          = QSizePolicy.Policy.Maximum

    # Misc
    Qt_KeepAspectRatio           = Qt.AspectRatioMode.KeepAspectRatio
    Qt_SmoothTransformation      = Qt.TransformationMode.SmoothTransformation
    Qt_ScrollBarAlwaysOff        = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    Qt_WaitCursor                = Qt.CursorShape.WaitCursor
    Qt_ArrowCursor               = Qt.CursorShape.ArrowCursor
    Qt_PointingHandCursor        = Qt.CursorShape.PointingHandCursor
    Qt_Checked                   = Qt.CheckState.Checked
    Qt_Unchecked                 = Qt.CheckState.Unchecked
    Qt_RichText                  = Qt.TextFormat.RichText
    Qt_PlainText                 = Qt.TextFormat.PlainText
    Qt_TextBrowserInteraction    = Qt.TextInteractionFlag.TextBrowserInteraction
    Qt_transparent               = Qt.GlobalColor.transparent

else:
    # Window flags
    Qt_Window                    = Qt.Window
    Qt_Dialog                    = Qt.Dialog
    Qt_WindowMinimizeButtonHint  = Qt.WindowMinimizeButtonHint
    Qt_WindowMaximizeButtonHint  = Qt.WindowMaximizeButtonHint
    Qt_WindowCloseButtonHint     = Qt.WindowCloseButtonHint
    Qt_WindowStaysOnTopHint      = Qt.WindowStaysOnTopHint

    # Alignment
    Qt_AlignCenter               = Qt.AlignCenter
    Qt_AlignLeft                 = Qt.AlignLeft
    Qt_AlignRight                = Qt.AlignRight
    Qt_AlignTop                  = Qt.AlignTop
    Qt_AlignBottom               = Qt.AlignBottom
    Qt_AlignVCenter              = Qt.AlignVCenter
    Qt_AlignHCenter              = Qt.AlignHCenter

    # Orientation
    Qt_Horizontal                = Qt.Horizontal
    Qt_Vertical                  = Qt.Vertical

    # Item roles / flags
    Qt_UserRole                  = Qt.UserRole
    Qt_DisplayRole               = Qt.DisplayRole
    Qt_CheckStateRole            = Qt.CheckStateRole
    Qt_ItemIsEditable            = Qt.ItemIsEditable
    Qt_ItemIsEnabled             = Qt.ItemIsEnabled
    Qt_ItemIsSelectable          = Qt.ItemIsSelectable

    # Mouse buttons
    Qt_LeftButton                = Qt.LeftButton
    Qt_RightButton               = Qt.RightButton
    Qt_MiddleButton              = Qt.MiddleButton

    # QFrame shapes
    QFrame_NoFrame               = QFrame.NoFrame
    QFrame_HLine                 = QFrame.HLine
    QFrame_VLine                 = QFrame.VLine
    QFrame_StyledPanel           = QFrame.StyledPanel
    QFrame_Panel                 = QFrame.Panel
    QFrame_Box                   = QFrame.Box

    # QLineEdit echo modes
    QLineEdit_Normal             = QLineEdit.Normal
    QLineEdit_Password           = QLineEdit.Password
    QLineEdit_NoEcho             = QLineEdit.NoEcho
    QLineEdit_PasswordEchoOnEdit = QLineEdit.PasswordEchoOnEdit

    # QPainter render hints
    QPainter_Antialiasing        = QPainter.Antialiasing
    QPainter_TextAntialiasing    = QPainter.TextAntialiasing
    QPainter_SmoothPixmapTransform = QPainter.SmoothPixmapTransform

    # QMessageBox
    QMessageBox_Information      = QMessageBox.Information
    QMessageBox_Question         = QMessageBox.Question
    QMessageBox_Warning          = QMessageBox.Warning
    QMessageBox_Critical         = QMessageBox.Critical
    QMessageBox_Yes              = QMessageBox.Yes
    QMessageBox_No               = QMessageBox.No
    QMessageBox_Ok               = QMessageBox.Ok
    QMessageBox_Cancel           = QMessageBox.Cancel

    # QDialog
    QDialog_Accepted             = QDialog.Accepted
    QDialog_Rejected             = QDialog.Rejected

    # Window types / widget attributes
    Qt_Tool                      = Qt.Tool
    Qt_FramelessWindowHint       = Qt.FramelessWindowHint
    Qt_WA_TranslucentBackground  = Qt.WA_TranslucentBackground

    # Pen styles
    Qt_SolidLine                 = Qt.SolidLine

    # Keyboard keys
    Qt_Key_Escape                = Qt.Key_Escape
    Qt_Key_Backspace             = Qt.Key_Backspace
    Qt_Key_Delete                = Qt.Key_Delete
    Qt_Key_Return                = Qt.Key_Return
    Qt_Key_Enter                 = Qt.Key_Enter

    # QSizePolicy
    QSizePolicy_Expanding        = QSizePolicy.Expanding
    QSizePolicy_Preferred        = QSizePolicy.Preferred
    QSizePolicy_Fixed            = QSizePolicy.Fixed
    QSizePolicy_Minimum          = QSizePolicy.Minimum
    QSizePolicy_Maximum          = QSizePolicy.Maximum

    # Misc
    Qt_KeepAspectRatio           = Qt.KeepAspectRatio
    Qt_SmoothTransformation      = Qt.SmoothTransformation
    Qt_ScrollBarAlwaysOff        = Qt.ScrollBarAlwaysOff
    Qt_WaitCursor                = Qt.WaitCursor
    Qt_ArrowCursor               = Qt.ArrowCursor
    Qt_PointingHandCursor        = Qt.PointingHandCursor
    Qt_Checked                   = Qt.Checked
    Qt_Unchecked                 = Qt.Unchecked
    Qt_RichText                  = Qt.RichText
    Qt_PlainText                 = Qt.PlainText
    Qt_TextBrowserInteraction    = Qt.TextBrowserInteraction
    Qt_transparent               = Qt.transparent