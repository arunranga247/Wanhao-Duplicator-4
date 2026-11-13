"""
Duplicator 4 Studio (Qt) - printer software for the Wanhao Duplicator 4 (Sailfish, USB).

    python tools/d4_qt.py                 the app
    python tools/d4_qt.py --selftest      check the bundled tools + window (writes output/selftest.txt)

Tabs
  Printer  - live temperatures + chart, limit switches, move/home, extruders, filament, log
  Prepare  - make a print (your 3D model through PrusaSlicer, or built-in test objects) with a
             real-time 3D viewer (GPU), fit check, safety check
  Print    - file library with preview/time/filament/check, pre-print checklist, live print view

Safety: EMERGENCY STOP (button / Esc), heater watchdog (in the worker), bed heating refused when
switched off or when the bed sensor reads below room temperature, files that fail the checker
cannot be printed. All rules live in d4_core (tested in tools/tests).
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import collections
import html
import os
import queue
import shutil
import sys
import threading
import time
import traceback
import webbrowser

import numpy as np
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (QColor, QFont, QIcon, QImage, QKeySequence, QMatrix4x4, QPainter, QPainterPath,
                           QPalette, QPen, QPixmap, QShortcut, QSurfaceFormat, QVector3D)
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QRadioButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QStackedLayout, QStatusBar,
                               QTabWidget, QTextEdit, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

import d4_core as core
import d4_paths
import render_preview as rp
import s3g_link as s3g
from d4_paths import LOGFILE, OUT, PREV, run_tool
from d4_worker import Worker

THEME_CHOICE = core.load_settings().get("theme", "System")
if THEME_CHOICE not in core.THEME_CHOICES:
    THEME_CHOICE = "System"
THEME = core.resolve_theme(THEME_CHOICE)
COL = dict(core.PALETTES[THEME])            # current colours; changed in place on a theme switch
MODEL_EXT = (".stl", ".3mf", ".obj")


# =============================================================================================
# Theme: Fusion style + palette + one style sheet. Switching = set both again (instant, live).
# =============================================================================================
def make_palette(P):
    pal = QPalette()
    c = lambda k: QColor(P[k])                                          # noqa: E731
    for role, key in ((QPalette.ColorRole.Window, "page"), (QPalette.ColorRole.WindowText, "fg"),
                      (QPalette.ColorRole.Base, "field"), (QPalette.ColorRole.AlternateBase, "page"),
                      (QPalette.ColorRole.Text, "fg"), (QPalette.ColorRole.Button, "btn"),
                      (QPalette.ColorRole.ButtonText, "fg"), (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.HighlightedText, "on_accent"), (QPalette.ColorRole.ToolTipBase, "bg"),
                      (QPalette.ColorRole.ToolTipText, "fg"), (QPalette.ColorRole.PlaceholderText, "dim"),
                      (QPalette.ColorRole.Link, "accent"), (QPalette.ColorRole.Mid, "border"),
                      (QPalette.ColorRole.Light, "bg"), (QPalette.ColorRole.Midlight, "grid"),
                      (QPalette.ColorRole.Dark, "border"), (QPalette.ColorRole.Shadow, "border")):
        pal.setColor(role, c(key))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, c("dis_fg"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, c("btn_dis"))
    return pal


def stylesheet(P):
    return """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: %(fg)s; }
QMainWindow, QWidget#page, QWidget#tabPage { background: %(page)s; }
QWidget#header { background: %(bg)s; border-bottom: 1px solid %(border)s; }
QLabel { background: transparent; }
QLabel#appTitle { font-size: 15pt; font-weight: 700; }
QLabel#cardTitle { font-size: 11pt; font-weight: 600; padding: 0 0 2px 4px; }
QLabel#big { font-size: 20pt; font-weight: 600; }
QLabel#value { font-size: 13pt; font-weight: 700; }
QLabel#jobTitle { font-size: 17pt; font-weight: 600; }
QLabel#mono, QLabel#fileInfo { font-family: Consolas; font-size: 9pt; }
QLabel[tone="dim"] { color: %(dim)s; }
QLabel[tone="ok"] { color: %(ok)s; }
QLabel[tone="warn"] { color: %(warn)s; }
QLabel[tone="bad"] { color: %(r)s; }
QLabel#pill { border-radius: 10px; padding: 2px 10px; font-size: 9pt; font-weight: 600; }
QLabel#pill[on="true"] { background: %(ok)s; color: %(on_accent)s; }
QLabel#pill[on="false"] { background: %(field)s; color: %(dim)s; }
QFrame#card { background: %(bg)s; border: 1px solid %(border)s; border-radius: 10px; }
QFrame#sep { background: %(border)s; max-height: 1px; min-height: 1px; border: none; }
QPushButton { background: %(btn)s; border: 1px solid %(border)s; border-radius: 6px; padding: 5px 12px; }
QPushButton:hover { background: %(btn_active)s; }
QPushButton:pressed { background: %(grid)s; }
QPushButton:disabled { color: %(dis_fg)s; background: %(btn_dis)s; border-color: %(grid)s; }
QPushButton[kind="filled"] { background: %(accent)s; color: %(on_accent)s; border: none; font-weight: 600; padding: 7px 18px; }
QPushButton[kind="filled"]:hover { background: %(accent2)s; }
QPushButton[kind="tonal"] { background: %(tonal)s; color: %(tonal_fg)s; border: none; font-weight: 600; }
QPushButton[kind="tonal"]:hover { background: %(grid)s; }
QPushButton[kind="seg"] { background: transparent; border: 1px solid %(border)s; border-radius: 14px;
    padding: 3px 12px; color: %(dim)s; font-weight: 600; }
QPushButton[kind="seg"]:checked { background: %(tonal)s; color: %(tonal_fg)s; border-color: %(tonal)s; }
QPushButton[kind="danger"] { background: %(danger)s; color: #ffffff; border: none; font-weight: 700; font-size: 11pt; padding: 7px 18px; }
QPushButton[kind="danger"]:hover { background: %(danger2)s; }
QPushButton[kind="filled"]:disabled, QPushButton[kind="tonal"]:disabled { background: %(btn_dis)s; color: %(dis_fg)s; }
QLineEdit { background: %(field)s; border: 1px solid %(border)s; border-radius: 5px; padding: 3px 6px;
    min-height: 20px; selection-background-color: %(accent)s; }
QLineEdit:focus { border: 1px solid %(accent)s; }
QSpinBox, QDoubleSpinBox, QComboBox { min-height: 22px; font-family: 'Segoe UI'; font-size: 10pt; }
QComboBox QAbstractItemView { font-family: 'Segoe UI'; font-size: 10pt; }
QComboBox[tone="dim"] { color: %(dim)s; font-style: italic; }
QToolButton#info { background: %(tonal)s; color: %(tonal_fg)s; border: none; border-radius: 13px;
    font-family: 'Segoe UI'; font-size: 11pt; font-weight: 700; min-width: 26px; max-width: 26px;
    min-height: 26px; max-height: 26px; padding: 0; }
QToolButton#info:hover { background: %(accent)s; color: %(on_accent)s; }
QToolButton#help { background: %(tonal)s; color: %(tonal_fg)s; border: none; border-radius: 8px;
    font-family: 'Segoe UI'; font-size: 7.5pt; font-weight: 700; min-width: 16px; max-width: 16px;
    min-height: 16px; max-height: 16px; padding: 0; }
QToolButton#help:hover { background: %(accent)s; color: %(on_accent)s; }
QPlainTextEdit#fileInfo { background: transparent; border: none; font-family: Consolas; font-size: 9pt; }
QComboBox QAbstractItemView { background: %(bg)s; border: 1px solid %(border)s;
    selection-background-color: %(tonal)s; selection-color: %(tonal_fg)s; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: %(dim)s; padding: 9px 22px; font-weight: 600; font-size: 10.5pt;
    border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: %(fg)s; border-bottom: 3px solid %(accent)s; }
QTabBar::tab:hover { color: %(fg)s; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QProgressBar { background: %(trough)s; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }
QProgressBar::chunk { background: %(accent)s; border-radius: 3px; }
QProgressBar[heater="r"]::chunk { background: %(r)s; }
QProgressBar[heater="l"]::chunk { background: %(l)s; }
QProgressBar[heater="bed"]::chunk { background: %(bed)s; }
QProgressBar#jobBar { max-height: 10px; min-height: 10px; border-radius: 5px; }
QProgressBar#jobBar::chunk { border-radius: 5px; }
QProgressBar[done="true"]::chunk { background: %(ok)s; }
QTreeWidget { background: %(canvas)s; border: 1px solid %(border)s; border-radius: 6px; outline: 0; }
QTreeWidget::item { padding: 5px 2px; }
QTreeWidget::item:selected { background: %(tonal)s; color: %(tonal_fg)s; }
QHeaderView::section { background: %(bg)s; color: %(dim)s; border: none; border-bottom: 1px solid %(border)s;
    padding: 5px; font-weight: 600; }
QTextEdit#log { background: %(canvas)s; border: none; font-family: Consolas; font-size: 9pt; }
QStatusBar { background: %(status)s; border-top: 1px solid %(border)s; }
QStatusBar QLabel { color: %(dim)s; font-size: 9pt; }
QToolTip { background: %(bg)s; color: %(fg)s; border: 1px solid %(border)s; }
QDialog, QMessageBox { background: %(bg)s; }
""" % P


def restyle(w):
    """Re-apply the style sheet after a dynamic property changed."""
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def set_tone(label, tone):
    if label.property("tone") != tone:
        label.setProperty("tone", tone)
        restyle(label)


def app_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#1a73e8"))
    p.setPen(QPen(QColor("white"), 2))
    p.drawEllipse(2, 2, 60, 60)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", 20)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, 64, 60), Qt.AlignmentFlag.AlignCenter, "D4")
    p.end()
    return QIcon(pm)


# =============================================================================================
# Small widgets
# =============================================================================================
class NoWheelSpin(QSpinBox):
    """Scrolling the page must never change a temperature: the wheel only works after a click."""

    def __init__(self, lo, hi, step=1, value=0):
        super().__init__()
        self.setRange(lo, hi)
        self.setSingleStep(step)
        self.setValue(value)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(68)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class NoWheelDouble(QDoubleSpinBox):
    def __init__(self, lo, hi, step, value, decimals):
        super().__init__()
        self.setDecimals(decimals)
        self.setRange(lo, hi)
        self.setSingleStep(step)
        self.setValue(value)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(78)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class NoWheelCombo(QComboBox):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e):
        if self.hasFocus() and self.view().isVisible():
            super().wheelEvent(e)
        else:
            e.ignore()


def button(text, slot=None, kind=None, tip=None):
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def label(text="", tone=None, name=None, wrap=False):
    lb = QLabel(text)
    if tone:
        lb.setProperty("tone", tone)
    if name:
        lb.setObjectName(name)
    if wrap:
        lb.setWordWrap(True)
    return lb


def card(title):
    """Card: title above a rounded panel. Returns (outer widget, body layout)."""
    outer = QWidget()
    v = QVBoxLayout(outer)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    v.addWidget(label(title, name="cardTitle"))
    fr = QFrame()
    fr.setObjectName("card")
    v.addWidget(fr, 1)
    body = QVBoxLayout(fr)
    body.setContentsMargins(14, 12, 14, 12)
    body.setSpacing(8)
    return outer, body


def separator():
    s = QFrame()
    s.setObjectName("sep")
    return s


class Dot(QWidget):
    """Coloured status circle (heater colour, limit switch on/off) with an optional letter."""

    def __init__(self, key=None, letter="", size=14):
        super().__init__()
        self.key, self.letter, self.on = key, letter, False
        self.setFixedSize(size, size)

    def set_on(self, on):
        if on != self.on:
            self.on = on
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = COL[self.key] if self.key else (COL["ok"] if self.on else COL["off"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(col))
        p.drawEllipse(QRectF(1, 1, self.width() - 2, self.height() - 2))
        if self.letter:
            p.setPen(QColor(COL["on_accent"] if self.on else COL["dim"]))
            f = QFont("Segoe UI", 10)
            f.setBold(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.letter)
        p.end()


class TempChart(QWidget):
    """Last 5 minutes of temperatures; solid = measured, dashed = target. Antialiased."""

    def __init__(self, hist):
        super().__init__()
        self.hist = hist
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(COL["canvas"]))
        ml, mr, mt, mb, tmax = 36, 8, 8, 20, 250
        now = time.time()
        X = lambda t: ml + (w - ml - mr) * (1 - (now - t) / core.CHART_SPAN_S)      # noqa: E731
        Y = lambda v: mt + (h - mt - mb) * (1 - v / tmax)                          # noqa: E731
        f = QFont("Segoe UI", 8)
        p.setFont(f)
        for v in range(0, tmax + 1, 50):
            p.setPen(QPen(QColor(COL["grid"]), 1))
            p.drawLine(QPointF(ml, Y(v)), QPointF(w - mr, Y(v)))
            p.setPen(QColor(COL["dim"]))
            p.drawText(QRectF(0, Y(v) - 8, ml - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(v))
        for m in range(0, 6):
            x = X(now - m * 60)
            p.drawText(QRectF(x - 30, h - 18, 30 if m == 0 else 60, 16),
                       Qt.AlignmentFlag.AlignRight if m == 0 else Qt.AlignmentFlag.AlignHCenter,
                       "now" if m == 0 else "-%dm" % m)
        for idx, key in ((1, "r"), (2, "l"), (3, "bed")):
            for col, dashed in ((idx + 3, True), (idx, False)):
                path, started = QPainterPath(), False
                for r in self.hist:
                    v = r[col]
                    if v is None or (dashed and not v):
                        started = False
                        continue
                    pt = QPointF(X(r[0]), Y(max(0, min(tmax, v))))
                    if started:
                        path.lineTo(pt)
                    else:
                        path.moveTo(pt)
                        started = True
                pen = QPen(QColor(COL[key]), 1.2 if dashed else 2.2)
                if dashed:
                    pen.setDashPattern([3, 3])
                p.setPen(pen)
                p.drawPath(path)
        p.end()


class ImageView(QLabel):
    """Shows a picture scaled to fit (tool-path previews)."""

    def __init__(self, text=""):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.src = None
        self.setProperty("tone", "dim")

    def set_image(self, path_or_qimage):
        if isinstance(path_or_qimage, QImage):
            self.src = QPixmap.fromImage(path_or_qimage)
        else:
            self.src = QPixmap(path_or_qimage) if path_or_qimage and os.path.exists(path_or_qimage) else None
        self._fit()

    def set_text(self, text):
        self.src = None
        self.clear()
        self.setText(text)

    def _fit(self):
        if self.src and not self.src.isNull():
            self.setPixmap(self.src.scaled(self.width() - 4, self.height() - 4, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


# =============================================================================================
# 3D model viewer: OpenGL (GPU, smooth at any size) with a CPU fallback
# =============================================================================================
VERT = """
#version 120
attribute vec3 pos;
attribute vec3 nrm;
attribute vec3 col;
uniform mat4 mvp;
uniform mat4 mv;
varying vec3 vN;
varying vec3 vP;
varying vec3 vC;
void main() {
    vC = col;
    vN = (mv * vec4(nrm, 0.0)).xyz;
    vP = (mv * vec4(pos, 1.0)).xyz;
    gl_Position = mvp * vec4(pos, 1.0);
}
"""
FRAG = """
#version 120
uniform vec3 color;
uniform float lit;
uniform float vcol;
varying vec3 vN;
varying vec3 vP;
varying vec3 vC;
void main() {
    if (lit < 0.5) { gl_FragColor = vec4(vcol > 0.5 ? vC : color, 1.0); return; }
    vec3 n = normalize(vN);
    vec3 v = normalize(-vP);
    if (dot(n, v) < 0.0) n = -n;                       // two-sided: open meshes look right too
    vec3 L = normalize(vec3(-0.45, 0.65, 0.65));
    float d = max(dot(n, L), 0.0);
    float f = max(dot(n, v), 0.0);
    vec3 h = normalize(L + v);
    float s = pow(max(dot(n, h), 0.0), 48.0) * 0.22;
    gl_FragColor = vec4(color * (0.28 + 0.47 * d + 0.30 * f) + vec3(s), 1.0);
}
"""
GL_FLOAT, GL_TRIANGLES, GL_LINES = 0x1406, 4, 1
GL_DEPTH_TEST, GL_COLOR_BIT, GL_DEPTH_BIT, GL_POLY_OFFSET = 0x0B71, 0x4000, 0x0100, 0x8037
MODEL_RGB = (0.92, 0.55, 0.18)
VIEW0 = {"yaw": -35.0, "pitch": 28.0, "zoom": 1.0, "px": 0.0, "py": 0.0}
PATH_RGB = {0: (0.92, 0.30, 0.28), 1: (0.24, 0.56, 0.92)}       # right nozzle red, left nozzle blue


class Toolpath:
    """Printing moves of an .x3g file, ready for the 3D viewer: coloured line segments sorted by
    layer, so 'show up to layer k' is simply 'draw the first n vertices'."""

    def __init__(self, path):
        segs, info = rp.decode(path)
        ext = np.array([s[:7] for s in segs if s[7]], dtype=np.float64)
        if not len(ext):
            raise ValueError("this file prints nothing (no extrusion moves)")
        p0, p1, tool = ext[:, 0:3], ext[:, 3:6], ext[:, 6].astype(int)
        # layers in 0.05 mm steps: real layers (0.1 mm and up) stay separate, while a spiral vase
        # (height rises on every move) does not become thousands of "layers"
        z = np.round(np.maximum(p0[:, 2], p1[:, 2]) / 0.05) * 0.05
        order = np.argsort(z, kind="stable")                    # layer by layer, in print order
        p0, p1, tool, z = p0[order], p1[order], tool[order], z[order]
        self.layers = np.unique(z)
        self.counts = np.searchsorted(z, self.layers, side="right") * 2      # vertices up to each layer
        zmin, zmax = float(self.layers[0]), float(self.layers[-1])
        shade = 0.55 + 0.45 * (z - zmin) / max(zmax - zmin, 1e-6)          # lower layers darker
        base = np.array([PATH_RGB.get(t, PATH_RGB[0]) for t in tool]) * shade[:, None]
        n = len(z)
        data = np.zeros((n * 2, 9), dtype=np.float32)
        data[0::2, 0:3], data[1::2, 0:3] = p0, p1
        data[:, 5] = 1.0
        data[0::2, 6:9] = data[1::2, 6:9] = base
        self.data = data
        # frame the object, not the purge line printed at the bed edge on the first layer
        above = z > zmin + 0.15
        pts = np.vstack([p0[above], p1[above]]) if above.sum() > 20 else np.vstack([p0, p1])
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        lo[2] = 0.0
        self.center = (lo + hi) / 2
        self.zc = float(self.center[2])
        self.radius = max(float(np.linalg.norm(hi - lo)) / 2, 5.0)
        used = sorted(set(tool.tolist()))
        self.info = "%d layers  ·  %.1f mm high  ·  %s" % (
            len(self.layers), zmax, " + ".join(("right nozzle (red)", "left nozzle (blue)")[t] for t in used if t in (0, 1)))


class ViewMixin:
    """Mouse: left-drag turn, right/middle-drag move, wheel zoom, double-click reset."""

    def _init_view(self):
        self.view = dict(VIEW0)
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(False)

    def mousePressEvent(self, e):
        self._drag = (e.position(), e.button(), dict(self.view))
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, _e):
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.view_done()

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        p0, btn, v0 = self._drag
        dx, dy = e.position().x() - p0.x(), e.position().y() - p0.y()
        if btn == Qt.MouseButton.LeftButton:
            self.view["yaw"] = (v0["yaw"] - dx * 0.5) % 360
            self.view["pitch"] = max(-85.0, min(89.0, v0["pitch"] + dy * 0.4))
        else:
            s = self.mm_per_px()
            self.view["px"] = v0["px"] - dx * s
            self.view["py"] = v0["py"] + dy * s
        self.view_changed()

    def wheelEvent(self, e):
        f = 1.15 ** (e.angleDelta().y() / 120.0)
        self.view["zoom"] = max(0.3, min(15.0, self.view["zoom"] * f))
        self.view_changed()
        self.view_done()
        e.accept()

    def mouseDoubleClickEvent(self, _e):
        self.reset_view()

    def reset_view(self):
        self.view = dict(VIEW0)
        self.view_changed()
        self.view_done()

    def view_done(self):
        pass


class GLViewer(ViewMixin, QOpenGLWidget):
    def __init__(self, on_fail):
        super().__init__()
        self._init_view()
        self.on_fail = on_fail
        self.ok = None                 # None = not initialised yet, True / False after initializeGL
        self.scene = None
        self._pending = None
        self.n_vert = 0
        self.mode = "mesh"             # "mesh" = 3D model, "paths" = print moves of an .x3g
        self.paths = None
        self.path_vert = 0             # how many path vertices to draw (layer slider)
        self.setMinimumSize(200, 150)
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)

    # ---- GL setup ----
    def initializeGL(self):
        try:
            self.f = self.context().functions()
            self.prog = QOpenGLShaderProgram(self)
            ok = (self.prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERT)
                  and self.prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAG))
            self.prog.bindAttributeLocation("pos", 0)
            self.prog.bindAttributeLocation("nrm", 1)
            self.prog.bindAttributeLocation("col", 2)
            if not (ok and self.prog.link()):
                raise RuntimeError("shader: " + self.prog.log())
            self.mesh_buf = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self.mesh_buf.create()
            self.bed_buf = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self.bed_buf.create()
            self.path_buf = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self.path_buf.create()
            self._upload_bed()
            self.ok = True
            if self._pending is not None:
                kind, obj = self._pending
                (self._upload_mesh if kind == "mesh" else self._upload_paths)(obj)
                self._pending = None
        except Exception as e:                                   # noqa: BLE001 - fall back to CPU drawing
            self.ok = False
            _crash_log("OpenGL viewer unavailable: %s\n" % e)
            QTimer.singleShot(0, self.on_fail)

    def _upload(self, buf, arr):
        data = np.ascontiguousarray(arr, dtype=np.float32)
        buf.bind()
        buf.allocate(data.tobytes(), data.nbytes)
        buf.release()

    def _upload_bed(self):
        hx, hy = 225.0 / 2, 145.0 / 2                           # Duplicator 4 bed, centred like the model
        quad = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, -hy), (hx, hy), (-hx, hy)]
        lines = []
        for gx in np.arange(-hx, hx + 0.1, 25.0):
            lines += [(gx, -hy), (gx, hy)]
        for gy in np.arange(-hy, hy + 0.1, 25.0):
            lines += [(-hx, gy), (hx, gy)]
        lines += [(-hx, -hy), (hx, -hy), (hx, -hy), (hx, hy), (hx, hy), (-hx, hy), (-hx, hy), (-hx, -hy)]
        pts = [(x, y, -0.05) for x, y in quad] + [(x, y, 0.0) for x, y in lines]
        arr = np.array([(x, y, z, 0, 0, 1) for x, y, z in pts], dtype=np.float32)
        self.n_quad, self.n_lines = len(quad), len(lines)
        self._upload(self.bed_buf, arr)

    def _upload_mesh(self, scene):
        v = scene.P[scene.T].reshape(-1, 3)
        n = np.repeat(scene.n, 3, axis=0)
        self._upload(self.mesh_buf, np.hstack([v, n]))
        self.n_vert = len(v)

    def _upload_paths(self, tp):
        self._upload(self.path_buf, tp.data)
        self.path_vert = int(tp.counts[-1])

    def _show(self, kind, obj):
        if self.ok:
            self.makeCurrent()
            (self._upload_mesh if kind == "mesh" else self._upload_paths)(obj)
            self.doneCurrent()
        else:
            self._pending = (kind, obj)
        self.update()

    def set_scene(self, scene):
        self.scene, self.mode = scene, "mesh"
        self.view = dict(VIEW0)
        self._show("mesh", scene)

    def set_paths(self, tp):
        self.paths, self.mode = tp, "paths"
        self.view = dict(VIEW0)
        self.path_vert = int(tp.counts[-1])
        self._show("paths", tp)

    def set_layer(self, k):
        """Show the print up to layer k (0-based)."""
        if self.paths is not None:
            self.path_vert = int(self.paths.counts[max(0, min(k, len(self.paths.counts) - 1))])
            self.update()

    # ---- camera ----
    def _camera(self):
        sc = self.paths if self.mode == "paths" else self.scene
        radius = sc.radius if sc else 50.0
        center = np.array(getattr(sc, "center", (0.0, 0.0, sc.zc if sc else 10.0)), dtype=float)
        fov = 30.0
        dist = radius / np.sin(np.radians(fov / 2)) * 1.1 / self.view["zoom"]
        yaw, pitch = np.radians(self.view["yaw"]), np.radians(self.view["pitch"])
        fwd = np.array([np.cos(pitch) * np.sin(yaw), -np.cos(pitch) * np.cos(yaw), np.sin(pitch)])  # target -> eye
        right = np.array([np.cos(yaw), np.sin(yaw), 0.0])                                         # screen right
        up = np.cross(fwd, right)                                                                 # screen up
        target = center + right * self.view["px"] + up * self.view["py"]
        eye = target + fwd * dist
        return target, eye, dist, fov

    def mm_per_px(self):
        _t, _e, dist, fov = self._camera()
        return 2 * dist * np.tan(np.radians(fov / 2)) / max(1, self.height())

    def paintGL(self):
        bg = QColor(COL["canvas"])
        f = self.f if self.ok else None
        if not f:
            return
        dpr = self.devicePixelRatioF()
        f.glViewport(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        f.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
        f.glClear(GL_COLOR_BIT | GL_DEPTH_BIT)
        f.glEnable(GL_DEPTH_TEST)
        target, eye, dist, fov = self._camera()
        proj = QMatrix4x4()
        proj.perspective(fov, self.width() / max(1, self.height()), max(0.05, dist * 0.01), dist * 10 + 600)
        view = QMatrix4x4()
        view.lookAt(QVector3D(*eye), QVector3D(*target), QVector3D(0, 0, 1))
        mvp = proj * view
        pr = self.prog
        pr.bind()
        pr.setUniformValue(pr.uniformLocation("mvp"), mvp)
        pr.setUniformValue(pr.uniformLocation("mv"), view)
        loc_col, loc_lit = pr.uniformLocation("color"), pr.uniformLocation("lit")
        loc_vcol = pr.uniformLocation("vcol")
        pr.setUniformValue1f(loc_vcol, 0.0)
        dark = bg.lightnessF() < 0.5
        # bed plate + grid (plate pushed back a little so the grid lines win)
        self._attrs(self.bed_buf)
        bed_fill = bg.lighter(135) if dark else bg.darker(112)
        bed_line = bg.lighter(175) if dark else bg.darker(140)
        pr.setUniformValue1f(loc_lit, 0.0)
        f.glEnable(GL_POLY_OFFSET)
        f.glPolygonOffset(1.0, 1.0)
        pr.setUniformValue(loc_col, QVector3D(bed_fill.redF(), bed_fill.greenF(), bed_fill.blueF()))
        f.glDrawArrays(GL_TRIANGLES, 0, self.n_quad)
        f.glDisable(GL_POLY_OFFSET)
        pr.setUniformValue(loc_col, QVector3D(bed_line.redF(), bed_line.greenF(), bed_line.blueF()))
        f.glDrawArrays(GL_LINES, self.n_quad, self.n_lines)
        if self.mode == "mesh" and self.n_vert:
            self._attrs(self.mesh_buf)
            pr.setUniformValue1f(loc_lit, 1.0)
            pr.setUniformValue(loc_col, QVector3D(*MODEL_RGB))
            f.glDrawArrays(GL_TRIANGLES, 0, self.n_vert)
        elif self.mode == "paths" and self.path_vert:
            self._attrs(self.path_buf, colours=True)
            pr.setUniformValue1f(loc_lit, 0.0)
            pr.setUniformValue1f(loc_vcol, 1.0)
            f.glLineWidth(1.6)
            f.glDrawArrays(GL_LINES, 0, self.path_vert)
            f.glLineWidth(1.0)
            self.prog.disableAttributeArray(2)
        pr.release()

    def _attrs(self, buf, colours=False):
        buf.bind()
        stride = 36 if colours else 24
        self.prog.enableAttributeArray(0)
        self.prog.enableAttributeArray(1)
        self.prog.setAttributeBuffer(0, GL_FLOAT, 0, 3, stride)
        self.prog.setAttributeBuffer(1, GL_FLOAT, 12, 3, stride)
        if colours:
            self.prog.enableAttributeArray(2)
            self.prog.setAttributeBuffer(2, GL_FLOAT, 24, 3, stride)
        else:
            self.prog.disableAttributeArray(2)

    def view_changed(self):
        self.update()


class SoftViewer(ViewMixin, QLabel):
    """CPU fallback (no usable OpenGL, e.g. remote desktop): numpy renderer from model_preview."""

    def __init__(self):
        super().__init__()
        self._init_view()
        self.scene = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._draw(sharp=True))

    def set_scene(self, scene):
        self.scene = scene
        self.view = dict(VIEW0)
        self._draw(sharp=True)

    def mm_per_px(self):
        return (self.scene.radius * 2 if self.scene else 100) / max(1, min(self.width(), self.height()))

    def _draw(self, sharp):
        if not self.scene:
            return
        v = self.view
        img = self.scene.image(self.width(), self.height(), v["yaw"], v["pitch"], v["zoom"], bg=COL["canvas"],
                               fast=not sharp)
        data = img.convert("RGB").tobytes()
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888).copy()
        self.setPixmap(QPixmap.fromImage(qimg))

    def view_changed(self):
        self._draw(sharp=False)
        self._timer.start(250)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._timer.start(150)


class ModelArea(QWidget):
    """Preview box of the Prepare tab. Up to three views of the current job, switched with the
    buttons on top: the 3D model, the print paths in 3D (with a layer slider), the overview picture."""

    VIEWS = (("model", "🧊  3D model"), ("paths", "〰  Print paths"), ("picture", "🖼  Overview"))

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self.bar = QWidget()
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        self.btns = {}
        for key, text in self.VIEWS:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("kind", "seg")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_view(k))
            bl.addWidget(b)
            self.btns[key] = b
        bl.addStretch(1)
        outer.addWidget(self.bar)
        mid = QHBoxLayout()
        mid.setSpacing(6)
        holder = QWidget()
        self.stack = QStackedLayout(holder)
        mid.addWidget(holder, 1)
        self.layer_box = QWidget()                           # layer slider (print paths only)
        lv = QVBoxLayout(self.layer_box)
        lv.setContentsMargins(0, 0, 0, 0)
        self.layer_top = label("", tone="dim")
        self.layer_top.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.layer_slider = QSlider(Qt.Orientation.Vertical)
        self.layer_slider.setToolTip("Drag down to see the print layer by layer")
        self.layer_slider.valueChanged.connect(self._layer_changed)
        self.layer_z = label("", tone="dim")
        self.layer_z.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lv.addWidget(self.layer_top)
        lv.addWidget(self.layer_slider, 1, Qt.AlignmentFlag.AlignHCenter)
        lv.addWidget(self.layer_z)
        self.layer_box.setFixedWidth(64)
        mid.addWidget(self.layer_box)
        outer.addLayout(mid, 1)
        self.msg = label("Choose a 3D model or generate an object to see it here", tone="dim")
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setWordWrap(True)
        self.image = ImageView()
        self.stack.addWidget(self.msg)
        self.stack.addWidget(self.image)
        self.soft = None
        self.gl = None
        if os.environ.get("D4_NO_GL") != "1" and QApplication.platformName() not in ("offscreen", "minimal"):
            self.gl = GLViewer(self._gl_failed)
            self.stack.addWidget(self.gl)
        self.scene = self.paths = self.picture = None
        self.current = None
        self._update_bar()

    # ---- what can be shown -------------------------------------------------------------------
    def set_model(self, scene):
        """A new 3D model was chosen: older print results no longer belong to it."""
        self.scene, self.paths, self.picture = scene, None, None
        self.show_view("model")

    def set_result(self, paths, picture, keep_model):
        """Generate finished: show the print paths in 3D (or the picture if 3D is not possible)."""
        if not keep_model:
            self.scene = None
        self.paths, self.picture = paths, picture
        self.show_view("paths" if self.paths_possible() else "picture")

    def paths_possible(self):
        return self.paths is not None and self.gl is not None and self.gl.ok is not False

    def available(self):
        return {"model": self.scene is not None, "paths": self.paths_possible(),
                "picture": bool(self.picture and os.path.exists(self.picture))}

    def show_view(self, key):
        av = self.available()
        if not av.get(key):
            key = next((k for k, _ in self.VIEWS if av[k]), None)
        self.current = key
        if key == "model":
            v = self.viewer()
            self.stack.setCurrentWidget(v)
            v.set_scene(self.scene)
            if v is self.gl:
                QTimer.singleShot(3000, self._check_gl)
        elif key == "paths":
            self.stack.setCurrentWidget(self.gl)
            self.gl.set_paths(self.paths)
            n = len(self.paths.layers)
            self.layer_slider.blockSignals(True)
            self.layer_slider.setRange(0, n - 1)
            self.layer_slider.setValue(n - 1)
            self.layer_slider.blockSignals(False)
            self._layer_changed(n - 1)
            QTimer.singleShot(3000, self._check_gl)
        elif key == "picture":
            self.image.set_image(self.picture)
            self.stack.setCurrentWidget(self.image)
        self._update_bar()

    def _update_bar(self):
        av = self.available()
        for k, b in self.btns.items():
            b.setVisible(av[k])
            b.setChecked(k == self.current)
        self.bar.setVisible(sum(av.values()) >= 2)
        self.layer_box.setVisible(self.current == "paths")

    def _layer_changed(self, k):
        if self.paths is None:
            return
        n = len(self.paths.layers)
        self.layer_top.setText("Layer\n%d / %d" % (k + 1, n))
        self.layer_z.setText("%.2f\nmm" % self.paths.layers[k])
        if self.gl is not None:
            self.gl.set_layer(k)

    # ---- viewers -------------------------------------------------------------------------------
    def viewer(self):
        if self.gl is not None and self.gl.ok is not False:
            return self.gl
        if self.soft is None:
            self.soft = SoftViewer()
            self.stack.addWidget(self.soft)
        return self.soft

    def _gl_failed(self):
        if self.gl is not None:
            self.stack.removeWidget(self.gl)
            self.gl.deleteLater()
            self.gl = None
        self.show_view(self.current if self.current != "paths" else "picture")

    def _check_gl(self):
        """OpenGL context never came up (initializeGL not called): use the CPU renderer."""
        if self.gl is not None and self.gl.ok is None and self.gl.isVisible():
            self.gl.ok = False
            _crash_log("OpenGL viewer: no context after 3 s - using the CPU renderer\n")
            self._gl_failed()

    # ---- used by the window ----------------------------------------------------------------------
    def show_message(self, text):
        self.msg.setText(text)
        self.stack.setCurrentWidget(self.msg)
        self.current = None
        self.layer_box.setVisible(False)

    def show_scene(self, scene):
        self.scene = scene
        self.show_view("model")

    def show_picture(self, path):
        self.picture = path
        self.show_view("picture")

    def showing_model(self):
        return self.current == "model" and self.scene is not None

    def theme_changed(self):
        w = self.stack.currentWidget()
        if w is self.soft and self.soft is not None:
            self.soft._draw(sharp=True)
        elif w is self.gl and self.gl is not None:
            self.gl.update()


# =============================================================================================
# Little pictures for the "?" help of each setting (drawn once, cached as PNG next to previews)
# =============================================================================================
HELP_W, HELP_H = 168, 92
_INK, _SOFT, _RED, _BLUE, _ORANGE, _BED = "#3c4043", "#9aa0a6", "#ea4335", "#1a73e8", "#f29900", "#dadce0"


def _pen(p, col, w=1.6, dash=False):
    pen = QPen(QColor(col), w)
    if dash:
        pen.setDashPattern([3, 3])
    p.setPen(pen)


def _caption(p, x, y, w, text):
    p.setPen(QColor(_INK))
    f = QFont("Segoe UI", 7)
    p.setFont(f)
    p.drawText(QRectF(x, y, w, 14), Qt.AlignmentFlag.AlignHCenter, text)


def _draw_help(p, flag):
    W, H = HELP_W, HELP_H
    p.fillRect(QRectF(0, 0, W, H), QColor("#ffffff"))
    if flag == "layer-height":
        for i in range(10):                                   # thin layers
            p.fillRect(QRectF(22, 66 - i * 5, 40, 4), QColor(_ORANGE if i % 2 else "#f6b26b"))
        for i in range(4):                                    # thick layers
            p.fillRect(QRectF(104, 61 - i * 12.5, 40, 11), QColor(_ORANGE if i % 2 else "#f6b26b"))
        _caption(p, 2, 74, 80, "0.1 fine / smooth")
        _caption(p, 84, 74, 80, "0.3 draft / fast")
    elif flag == "infill":
        for k, (x, pct) in enumerate(((14, "0 %"), (66, "20 %"), (118, "100 %"))):
            r = QRectF(x, 14, 38, 38)
            if k == 2:
                p.fillRect(r, QColor(_ORANGE))
            elif k == 1:
                _pen(p, "#f6b26b", 1.4)
                for d in range(-38, 39, 9):
                    p.drawLine(QPointF(x + max(0, d), 14 + max(0, -d)), QPointF(x + min(38, 38 + d), 14 + min(38, 38 - d)))
            _pen(p, _ORANGE, 2.2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            _caption(p, x - 10, 58, 58, pct)
    elif flag == "walls":
        for x, n, cap in ((22, 1, "1 wall"), (100, 3, "3 walls")):
            for i in range(n):
                _pen(p, _ORANGE, 2.0)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(x + i * 4, 12 + i * 4, 44 - i * 8, 44 - i * 8))
            _caption(p, x - 10, 62, 64, cap)
    elif flag == "supports":
        p.fillRect(QRectF(20, 60, 128, 3), QColor(_BED))
        p.fillRect(QRectF(30, 18, 26, 42), QColor(_ORANGE))           # post
        p.fillRect(QRectF(30, 18, 100, 12), QColor(_ORANGE))          # overhang arm
        _pen(p, _SOFT, 1.2, dash=True)
        for x in range(64, 128, 9):                                    # support pillars
            p.drawLine(QPointF(x, 31), QPointF(x, 59))
        _caption(p, 4, 68, 160, "dashed = support pillars (break off)")
    elif flag == "brim":
        _pen(p, "#f6b26b", 1.2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(4, 0, -1):
            p.drawRoundedRect(QRectF(54 - i * 6, 24 - i * 4, 60 + i * 12, 30 + i * 8), 6, 6)
        p.fillRect(QRectF(54, 24, 60, 30), QColor(_ORANGE))
        _caption(p, 4, 76, 160, "top view: brim rings round the part")
    elif flag == "scale":
        p.fillRect(QRectF(34, 40, 20, 20), QColor(_ORANGE))
        p.fillRect(QRectF(92, 12, 48, 48), QColor(_ORANGE))
        _caption(p, 14, 64, 60, "50 %")
        _caption(p, 86, 64, 60, "200 %")
    elif flag in ("temp", "first-temp"):
        path = QPainterPath()
        path.moveTo(64, 16)
        path.lineTo(104, 16)
        path.lineTo(90, 44)
        path.lineTo(78, 44)
        path.closeSubpath()
        p.setBrush(QColor("#9e9e9e"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
        _pen(p, _RED, 1.6)
        for dx in (-26, -18, 18, 26):                                  # heat waves
            x = 84 + dx
            w = QPainterPath()
            w.moveTo(x, 40)
            w.cubicTo(x - 4, 32, x + 4, 26, x, 18)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(w)
        if flag == "first-temp":
            p.fillRect(QRectF(40, 52, 88, 5), QColor(_ORANGE))
            p.fillRect(QRectF(30, 57, 108, 3), QColor(_BED))
            _caption(p, 4, 66, 160, "hotter first layer sticks better")
        else:
            p.fillRect(QRectF(40, 52, 88, 4), QColor(_ORANGE))
            p.fillRect(QRectF(40, 47, 88, 4), QColor("#f6b26b"))
            _caption(p, 4, 66, 160, "PLA 200 - 215 °C")
    elif flag == "z-offset":
        for x, gap, good in ((14, 16, False), (92, 4, True)):
            nz = QPainterPath()
            nz.moveTo(x + 14, 10)
            nz.lineTo(x + 46, 10)
            nz.lineTo(x + 34, 32 - (12 - gap))
            nz.lineTo(x + 26, 32 - (12 - gap))
            nz.closeSubpath()
            p.setBrush(QColor("#9e9e9e"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(nz)
            p.fillRect(QRectF(x, 54, 62, 3), QColor(_BED))
            if good:
                p.fillRect(QRectF(x + 4, 49, 54, 5), QColor(_ORANGE))     # flat, squished line
            else:
                p.setBrush(QColor(_ORANGE))
                for i in range(5):                                          # round loose strands
                    p.drawEllipse(QRectF(x + 6 + i * 11, 46, 7, 7))
            _caption(p, x - 6, 62, 74, "too high: strings" if not good else "right: flat")
    elif flag == "color-z":
        p.fillRect(QRectF(58, 38, 52, 22), QColor(_RED))
        p.fillRect(QRectF(58, 12, 52, 26), QColor(_BLUE))
        _pen(p, _INK, 1.2, dash=True)
        p.drawLine(QPointF(40, 38), QPointF(128, 38))
        _caption(p, 4, 66, 160, "above the line: the other nozzle")
    elif flag == "fast":
        _pen(p, _ORANGE, 3.0)
        for i in range(3):
            x = 46 + i * 26
            p.drawLine(QPointF(x, 18), QPointF(x + 18, 36))
            p.drawLine(QPointF(x + 18, 36), QPointF(x, 54))
        _caption(p, 4, 66, 160, "simple parts: about 40 % quicker")
    else:
        return False
    return True


def help_picture(flag):
    """PNG file with a little drawing that explains the setting, or None."""
    d = os.path.join(PREV, "_help")
    path = os.path.join(d, "%s.png" % flag.replace("/", "_"))
    if os.path.exists(path):
        return path
    pm = QPixmap(HELP_W * 2, HELP_H * 2)
    pm.setDevicePixelRatio(2)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    drawn = _draw_help(p, flag)
    p.end()
    if not drawn:
        return None
    os.makedirs(d, exist_ok=True)
    pm.save(path)
    return path


def help_html(title, flag):
    text = html.escape(core.PARAM_HELP.get(flag, "")).replace("\n", "<br>")
    pic = help_picture(flag)
    img = '<img src="%s" width="%d" height="%d"><br>' % (QUrl.fromLocalFile(pic).toString(), HELP_W, HELP_H) if pic else ""
    return "<b>%s</b><br>%s%s" % (html.escape(title), img, text)


# =============================================================================================
# Pre-print checklist
# =============================================================================================
class Checklist(QDialog):
    def __init__(self, parent, path, st):
        super().__init__(parent)
        self.setWindowTitle("Before printing")
        self.setModal(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 16)
        t = label("Before printing %s" % os.path.basename(path), name="jobTitle")
        v.addWidget(t)
        v.addWidget(label("Time ≈ %s + heat-up    filament R %.0f / L %.0f mm"
                          % (core.fmt_min(st["time_s"]), *st["fil"]), tone="dim"))
        self.boxes = []
        for it in core.checklist_items(st):
            cb = QCheckBox(it)
            cb.toggled.connect(self._upd)
            v.addWidget(cb)
            self.boxes.append(cb)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancel", self.reject))
        self.go = button("▶  Start print", self.accept, kind="filled")
        row.addWidget(self.go)
        v.addSpacing(8)
        v.addLayout(row)
        self._upd()

    def _upd(self):
        self.go.setEnabled(all(b.isChecked() for b in self.boxes))


# =============================================================================================
# Main window
# =============================================================================================
class MainWindow(QMainWindow):
    def __init__(self, worker=None):
        super().__init__()
        self.setWindowTitle("Duplicator 4 Studio")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 600)
        os.makedirs(PREV, exist_ok=True)
        self.events = queue.Queue()
        self.worker = worker or Worker(self.events)
        if worker is not None:
            worker.events = self.events
        if not self.worker.is_alive() and hasattr(self.worker, "start"):
            self.worker.start()
        self.hist = collections.deque()
        self.es_last, self.es_changes = None, collections.deque()
        self.connected = self.printing = self.user_disconnected = False
        self.print_stats, self.heat_phase, self.job_file = None, None, ""
        self._connecting_until = 0.0
        self._last_temps, self._last_pos = {}, [0.0] * 5
        self._controls, self._ports = [], []
        self._stats_cache, self._check_cache = {}, {}
        self._gen_name_done = None
        self._model_key = None
        self.ui = core.load_settings().get("ui", {})
        self._obj_params = dict(self.ui.get("obj_params", {}))
        self._build()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.estop).setContext(Qt.ShortcutContext.WindowShortcut)
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, self.show_about)
        self._restore_ui()
        self.refresh_ports(autoconnect=True)
        self.refresh_library(select=self.ui.get("last_file"))
        self.timers = []
        for ms, fn in ((100, self.pump), (3000, self.watch_ports), (15000, self.save_ui)):
            t = QTimer(self)
            t.timeout.connect(fn)
            t.start(ms)
            self.timers.append(t)

    # ---- dialogs (one place, so tests can answer them) -----------------------------------
    def info(self, title, text):
        QMessageBox.information(self, title, text)

    def warn(self, title, text):
        QMessageBox.warning(self, title, text)

    def error(self, title, text):
        QMessageBox.critical(self, title, text)

    def ask(self, title, text):
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def ask_ok(self, title, text):
        r = QMessageBox.question(self, title, text, QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        return r == QMessageBox.StandardButton.Ok

    def checklist(self, path, st):
        return Checklist(self, path, st).exec() == QDialog.DialogCode.Accepted

    def pick_file(self, title, start, filt):
        return QFileDialog.getOpenFileName(self, title, start, filt)[0]

    def pick_files(self, title, start, filt):
        return QFileDialog.getOpenFileNames(self, title, start, filt)[0]

    def open_url(self, path):
        webbrowser.open("file:///" + os.path.abspath(path).replace("\\", "/"))

    # ---- layout ---------------------------------------------------------------------------
    def _ctl(self, w):
        self._controls.append(w)
        return w

    def _build(self):
        central = QWidget()
        central.setObjectName("page")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget()
        head.setObjectName("header")
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(8)
        self.title_lbl = label("Duplicator 4 Studio", name="appTitle")
        self.title_lbl.mouseDoubleClickEvent = lambda e: self.show_about()
        h.addWidget(self.title_lbl)
        h.addSpacing(14)
        h.addWidget(label("Port"))
        self.port_box = NoWheelCombo()
        self.port_box.setMinimumWidth(230)
        self.port_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        h.addWidget(self.port_box)
        h.addWidget(button("↻", self.refresh_ports, tip="Look for printers again"))
        self.conn_btn = button("Connect", self.toggle_connect)
        h.addWidget(self.conn_btn)
        self.conn_lbl = label("● Disconnected", tone="dim")
        self.conn_lbl.setStyleSheet("font-weight: 700;")
        h.addWidget(self.conn_lbl)
        self.board_lbl = label("", tone="dim")
        h.addWidget(self.board_lbl)
        h.addStretch(1)
        self.estop_btn = button("⛔  EMERGENCY STOP  (Esc)", self.estop, kind="danger")
        self.estop_btn.setMinimumHeight(38)
        h.addWidget(self.estop_btn)
        root.addWidget(head)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)
        self.tab_printer = self._scroll_tab(self._build_printer_tab())
        self.tab_prepare = self._build_prepare_tab()             # scrolls inside (settings column)
        self.tab_print = self._scroll_tab(self._build_print_tab())
        self.tabs.addTab(self.tab_printer, "🖨  Printer")
        self.tabs.addTab(self.tab_prepare, "🧩  Prepare")
        self.tabs.addTab(self.tab_print, "📂  Print")

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_lbl = label("Ready")
        sb.addWidget(self.status_lbl, 1)
        self.status_temps = label("", name="mono")
        sb.addPermanentWidget(self.status_temps)
        sb.addPermanentWidget(label("  Theme"))
        self.theme_box = NoWheelCombo()
        self.theme_box.addItems(core.THEME_CHOICES)
        self.theme_box.setCurrentText(THEME_CHOICE)
        self.theme_box.currentTextChanged.connect(self.apply_theme)
        sb.addPermanentWidget(self.theme_box)
        self.set_controls(False)

    def _scroll_tab(self, content):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        content.setObjectName("tabPage")
        sa.setWidget(content)
        return sa

    # ======================= PRINTER TAB ====================================================
    def _build_printer_tab(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(12, 12, 12, 12)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(12)
        for c in range(3):
            g.setColumnStretch(c, 1)
        g.addWidget(self._build_temps(), 0, 0)
        g.addWidget(self._build_chart(), 1, 0)
        g.addWidget(self._build_switches(), 0, 1)
        g.addWidget(self._build_jog(), 1, 1)
        g.addWidget(self._build_extruders(), 0, 2)
        g.addWidget(self._build_log(), 1, 2)
        g.setRowStretch(1, 1)
        return page

    def _build_temps(self):
        outer, body = card("Temperatures")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(1, 1)
        self.t_lbl, self.t_tgt, self.t_entry, self.t_bar = {}, {}, {}, {}
        for i, (key, name, default, hi) in enumerate((("r", "Right", 210, core.NOZZLE_MAX_C),
                                                      ("l", "Left", 210, core.NOZZLE_MAX_C),
                                                      ("bed", "Bed", 0, core.BED_MAX_C))):
            r0 = i * 2
            grid.addWidget(Dot(key), r0, 0)
            nm = QVBoxLayout()
            nm.setSpacing(0)
            nm.addWidget(label(name, name=None))
            self.t_tgt[key] = label("off", tone="dim")
            nm.addWidget(self.t_tgt[key])
            grid.addLayout(nm, r0, 1)
            self.t_lbl[key] = label("---°", name="big")
            self.t_lbl[key].setMinimumWidth(78)
            self.t_lbl[key].setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(self.t_lbl[key], r0, 2)
            sp = NoWheelSpin(0, hi, 5, default)
            self.t_entry[key] = sp
            grid.addWidget(sp, r0, 3)
            grid.addWidget(button("Set", lambda _=False, k=key: self.set_heater(k)), r0, 4)
            grid.addWidget(button("Off", lambda _=False, k=key: self.set_heater(k, 0)), r0, 5)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 1000)
            bar.setValue(0)
            bar.setProperty("heater", key)
            self.t_bar[key] = bar
            grid.addWidget(bar, r0 + 1, 1, 1, 5)
        body.addLayout(grid)
        self.bed_ok = QCheckBox("Allow bed heating (max %d °C)" % core.BED_MAX_C)
        self.bed_ok.setToolTip("Even when ticked, bed heating is refused while the bed sensor reads below "
                               "%d °C (broken wire)." % core.BED_MIN_PLAUSIBLE_C)
        self.bed_ok.setChecked(True)
        body.addWidget(self.bed_ok)
        row = QHBoxLayout()
        row.addWidget(button("🔥 PLA: both 210 °C", lambda: self.preset(210)))
        row.addWidget(button("❄ All heaters off", lambda: self.worker.submit("heaters_off")))
        row.addStretch(1)
        body.addLayout(row)
        return outer

    def _build_chart(self):
        outer, body = card("Temperature history (5 min)")
        self.chart = TempChart(self.hist)
        body.addWidget(self.chart, 1)
        return outer

    def _build_switches(self):
        outer, body = card("Limit switches  &  position")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.sw = {}
        for i, (bit, letter, name, where) in enumerate(((1, "X", "X axis", "→|  head at the right end"),
                                                        (3, "Y", "Y axis", "↑|  head at the back"),
                                                        (4, "Z", "Z axis", "↑  bed at the top"))):
            d = Dot(None, letter, 28)
            grid.addWidget(d, i, 0)
            info = QVBoxLayout()
            info.setSpacing(0)
            info.addWidget(label(name))
            info.addWidget(label(where, tone="dim"))
            grid.addLayout(info, i, 1)
            pill = label("○  open", name="pill")
            pill.setProperty("on", "false")
            grid.addWidget(pill, i, 2)
            self.sw[bit] = (d, pill)
        body.addLayout(grid)
        self.sw_warn = label("", tone="warn")
        body.addWidget(self.sw_warn)
        body.addWidget(separator())
        self.pos_lbl = label("X ---   Y ---   Z ---", name="mono")
        body.addWidget(self.pos_lbl)
        self.homed_lbl = label("Not homed", tone="dim")
        body.addWidget(self.homed_lbl)
        body.addStretch(1)
        return outer

    def _set_switch(self, bit, on):
        d, pill = self.sw[bit]
        d.set_on(on)
        want = "true" if on else "false"
        if pill.property("on") != want:
            pill.setProperty("on", want)
            pill.setText("●  PRESSED" if on else "○  open")
            restyle(pill)

    def _build_jog(self):
        outer, body = card("Move")
        row = QHBoxLayout()
        row.addWidget(label("Step"))
        self.step_group = QButtonGroup(self)
        for v in (0.1, 1, 10, 50):
            rb = QRadioButton("%g mm" % v)
            rb.setProperty("mm", float(v))
            self.step_group.addButton(rb)
            row.addWidget(rb)
            if v == 10:
                rb.setChecked(True)
        row.addStretch(1)
        body.addLayout(row)
        g = QGridLayout()
        g.setSpacing(4)
        hx = label("Head  (X / Y)", tone="dim")
        hx.setAlignment(Qt.AlignmentFlag.AlignCenter)
        g.addWidget(hx, 0, 0, 1, 3)
        bz = label("Bed  (Z)", tone="dim")
        bz.setAlignment(Qt.AlignmentFlag.AlignCenter)
        g.addWidget(bz, 0, 4)
        g.setColumnMinimumWidth(3, 12)

        def B(text, slot, r, c, kind=None):
            b = self._ctl(button(text, slot, kind=kind))
            b.setMinimumHeight(32)
            g.addWidget(b, r, c)
        B("▲  Back", lambda: self.jog(1, +1), 1, 1)
        B("◄  Left", lambda: self.jog(0, -1), 2, 0)
        B("⌂  Home XY", lambda: self.worker.submit("home_xy"), 2, 1, kind="tonal")
        B("Right  ►", lambda: self.jog(0, +1), 2, 2)
        B("▼  Front", lambda: self.jog(1, -1), 3, 1)
        B("▲  Up", lambda: self.jog(2, -1), 1, 4)            # bed moves up = towards the nozzles
        B("⌂  Home Z", self.home_z, 2, 4, kind="tonal")
        B("▼  Down", lambda: self.jog(2, +1), 3, 4)
        body.addLayout(g)
        row = QHBoxLayout()
        row.addWidget(self._ctl(button("⌂  Home all", self.home_all)))
        row.addWidget(self._ctl(button("⊘  Motors off", lambda: self.worker.submit("motors_off"))))
        row.addWidget(self._ctl(button("⚙  Motor test", self.motor_test)))
        body.addLayout(row)
        body.addStretch(1)
        return outer

    def step_mm(self):
        b = self.step_group.checkedButton()
        return float(b.property("mm")) if b else 10.0

    def _build_extruders(self):
        outer, body = card("Extruders / filament")
        top = QHBoxLayout()
        top.addWidget(label("Move"))
        self.e_amt = NoWheelSpin(1, 100, 5, 10)
        top.addWidget(self.e_amt)
        top.addWidget(label("mm", tone="dim"))
        top.addSpacing(10)
        top.addWidget(label("Load temp"))
        self.fil_temp = NoWheelSpin(core.FILAMENT_MIN_C, core.FILAMENT_MAX_C, 5, 210)
        top.addWidget(self.fil_temp)
        top.addWidget(label("°C", tone="dim"))
        top.addStretch(1)
        body.addLayout(top)
        g = QGridLayout()
        g.setSpacing(4)
        for i, (tool, name) in enumerate(((0, "Right"), (1, "Left"))):
            g.addWidget(label(name), i, 0)
            g.addWidget(self._ctl(button("Retract", lambda _=False, t=tool: self.extrude(t, -1))), i, 1)
            g.addWidget(self._ctl(button("Extrude", lambda _=False, t=tool: self.extrude(t, +1))), i, 2)
            g.addWidget(self._ctl(button("⬇ Load", lambda _=False, t=tool: self.filament(t, "load"))), i, 3)
            g.addWidget(self._ctl(button("⬆ Unload", lambda _=False, t=tool: self.filament(t, "unload"))), i, 4)
        body.addLayout(g)
        row = QHBoxLayout()
        self.keep_hot = QCheckBox("Keep nozzle hot afterwards")
        row.addWidget(self.keep_hot)
        row.addStretch(1)
        row.addWidget(self._ctl(button("■ Stop filament", lambda: self.worker.submit("stop_motion"))))
        body.addLayout(row)
        body.addStretch(1)
        return outer

    def _build_log(self):
        outer, body = card("Log")
        self.logbox = QTextEdit()
        self.logbox.setObjectName("log")
        self.logbox.setReadOnly(True)
        self.logbox.setMinimumHeight(140)
        body.addWidget(self.logbox, 1)
        return outer

    # ======================= PREPARE TAB =====================================================
    def _build_prepare_tab(self):
        page = QWidget()
        page.setObjectName("tabPage")
        h = QHBoxLayout(page)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(12)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0)
        lv.setSpacing(12)
        o, b = card("1. Choose an object")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.obj_box = NoWheelCombo()
        self.obj_box.addItems(list(core.OBJECTS))
        self.obj_box.currentTextChanged.connect(lambda _t: self._build_params())
        row.addWidget(self.obj_box, 1)
        # the long description lives behind a small "i" button (hover = tooltip, click = full text)
        self.obj_info = QToolButton()
        self.obj_info.setObjectName("info")
        self.obj_info.setText("i")
        self.obj_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.obj_info.clicked.connect(self.show_object_info)
        row.addWidget(self.obj_info)
        b.addLayout(row)
        lv.addWidget(o)
        o, self.param_body = card("2. Settings")
        self.param_host = QWidget()
        self.param_body.addWidget(self.param_host)
        lv.addWidget(o)
        lv.addStretch(1)
        sa = QScrollArea()                               # cards 1 + 2 scroll if the window is short ...
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setWidget(left)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        col = QWidget()
        cv = QVBoxLayout(col)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(12)
        cv.addWidget(sa, 1)
        col.setMinimumWidth(510)
        col.setMaximumWidth(580)
        o, b = card("3. Generate")                        # ... the Generate button never does
        row = QHBoxLayout()
        row.addWidget(label("File name"))
        self.gen_name = QLineEdit()
        self.gen_name.setMaxLength(24)
        self.gen_name.setMinimumWidth(150)
        row.addWidget(self.gen_name, 1)
        row.addWidget(label(".x3g", tone="dim"))
        self.gen_btn = button("⚙  Generate", self.generate, kind="filled")
        row.addWidget(self.gen_btn)
        b.addLayout(row)
        cv.addWidget(o)
        h.addWidget(col)
        o, b = card("Preview")
        self.model_area = ModelArea()
        b.addWidget(self.model_area, 1)
        res = QHBoxLayout()
        self.gen_status = label("", tone="dim", wrap=True)
        self.gen_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        res.addWidget(self.gen_status, 1)
        self.gen_to_print = button("📂  Open in Print tab", self._goto_print_generated, kind="tonal")
        self.gen_to_print.hide()
        res.addWidget(self.gen_to_print, 0, Qt.AlignmentFlag.AlignBottom)
        b.addLayout(res)
        h.addWidget(o, 1)
        self._params_for = None
        self.param_widgets = {}
        self._build_params()
        return page

    def _build_params(self):
        self._remember_params()
        for w in self.param_host.findChildren(QWidget, "", Qt.FindChildOption.FindDirectChildrenOnly):
            w.hide()
            w.setParent(None)                             # the old object's settings go away
            w.deleteLater()
        old = self.param_host.layout()
        if old is not None:
            QWidget().setLayout(old)                      # hand the empty old layout to a throw-away widget
        g = QGridLayout(self.param_host)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)
        name = self.obj_box.currentText()
        obj = core.OBJECTS[name]
        saved = self._obj_params.get(name, {})
        self._params_for = name
        self.obj_info.setToolTip("<b>%s</b><br>%s" % (html.escape(name), html.escape(obj["desc"])))
        self.param_widgets = {}
        r0 = 0
        self.model_edit = None
        if obj.get("model"):
            g.addWidget(self._label("3D model file", "_model"), 0, 0)
            self.model_edit = QLineEdit(saved.get("_model", ""))
            self.model_edit.setPlaceholderText("STL, 3MF or OBJ file")
            self.model_edit.textChanged.connect(lambda _t: self._queue_model_preview())
            g.addWidget(self.model_edit, 0, 1, 1, 4)
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(button("📂 Browse…", self.pick_model, kind="tonal"))
            row.addWidget(button("🔍 Fit check", lambda: self.fit_check(), kind="tonal"))
            row.addWidget(button("🧩 Assembly…", self.fit_check_assembly, kind="tonal"))
            row.addStretch(1)
            g.addLayout(row, 1, 0, 1, 4)
            r0 = 2
        params = obj["params"]
        two = len(params) > 5
        for i, (flag, lab, default, lo, hi, step) in enumerate(params):
            r, c = (r0 + i // 2, (i % 2) * 2) if two else (r0 + i, 0)
            g.addWidget(self._label(lab, flag), r, c)
            dec = 0 if float(step).is_integer() and float(lo).is_integer() and float(default).is_integer() \
                else max(len(("%g" % step).split(".")[-1]) if "." in "%g" % step else 0, 1)
            v = core.parse_number(saved.get(flag, default))
            sp = NoWheelDouble(lo, hi, step, default if v is None else v, dec)
            g.addWidget(sp, r, c + 1)
            if not two:
                g.addWidget(label("%g … %g" % (lo, hi), tone="dim"), r, 2)
            self.param_widgets[flag] = (sp, lo, hi)
        row = r0 + ((len(params) + 1) // 2 if two else len(params))
        self.ext_group = QButtonGroup(self.param_host)
        self.ext_left = QRadioButton("Left", self.param_host)
        self.ext_right = QRadioButton("Right", self.param_host)
        for rb in (self.ext_left, self.ext_right):
            self.ext_group.addButton(rb)
            rb.setVisible(bool(obj["extruder"]))
        (self.ext_right if saved.get("_extruder") == "right" else self.ext_left).setChecked(True)
        if obj["extruder"]:
            g.addWidget(self._label("Extruder", "_extruder"), row, 0)
            er = QHBoxLayout()
            er.addWidget(self.ext_left)
            er.addWidget(self.ext_right)
            er.addStretch(1)
            g.addLayout(er, row, 1, 1, 3)
        g.setColumnStretch(4, 1)                          # spare width goes to the right edge, not a box
        self.gen_name.setEnabled(not obj.get("fixed_name"))
        self.gen_name.setText(saved.get("_name", obj["name"]))
        if obj.get("fixed_name"):
            self.gen_name.setText(obj["name"])
        if obj.get("model"):
            self._queue_model_preview()

    def _label(self, text, flag):
        """Setting name + a small '?' : hover = picture + explanation, click = the same in a box."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(label(text))
        if flag in core.PARAM_HELP:
            b = QToolButton()
            b.setObjectName("help")
            b.setText("?")
            b.setCursor(Qt.CursorShape.WhatsThisCursor)
            b.setToolTip(help_html(text, flag))
            b.clicked.connect(lambda _=False, t=text, f=flag: self.show_help(t, f))
            b.setProperty("flag", flag)
            h.addWidget(b)
        h.addStretch(1)
        return w

    def show_help(self, title, flag):
        self.info(title, help_html(title, flag))

    def show_object_info(self):
        name = self.obj_box.currentText()
        self.info(name, core.OBJECTS[name]["desc"])

    def extruder(self):
        return "right" if self.ext_right.isChecked() else "left"

    def model_path(self):
        return self.model_edit.text().strip().strip('"') if self.model_edit is not None else ""

    def _remember_params(self):
        obj = self._params_for
        if not obj or not self.param_widgets:
            return
        vals = {flag: "%g" % sp.value() for flag, (sp, lo, hi) in self.param_widgets.items()}
        vals["_extruder"] = self.extruder()
        if core.OBJECTS[obj].get("model"):
            vals["_model"] = self.model_path()
        if not core.OBJECTS[obj].get("fixed_name"):
            vals["_name"] = self.gen_name.text()
        self._obj_params[obj] = vals

    # ---- 3D viewer of the chosen model -------------------------------------------------------
    def _queue_model_preview(self):
        if not hasattr(self, "_mprev_timer"):
            self._mprev_timer = QTimer(self)
            self._mprev_timer.setSingleShot(True)
            self._mprev_timer.timeout.connect(self._start_model_preview)
        self._mprev_timer.start(400)

    def _start_model_preview(self):
        m = self.model_path()
        if not os.path.isfile(m) or os.path.splitext(m)[1].lower() not in MODEL_EXT:
            return
        key = "%s|%s" % (m, os.path.getmtime(m))
        if key == self._model_key and self.model_area.scene is not None:
            self.model_area.show_scene(self.model_area.scene)      # already loaded: just show it again
            self._show_model_info(m, self.model_area.scene)
            return
        self._model_key = key
        self.model_area.show_message("Loading %s …" % os.path.basename(m))
        threading.Thread(target=self._model_load_worker, args=(m, key), daemon=True).start()

    def _model_load_worker(self, model, key):
        try:
            import model_preview
            self.events.put(("model_scene", key, model, model_preview.Scene(model), None))
        except Exception as e:                                 # noqa: BLE001 - shown in the preview box
            self.events.put(("model_scene", key, model, None, "%s: %s" % (type(e).__name__, e)))

    def on_model_scene(self, key, model, scene, err):
        if key != self._model_key:
            return                                             # an older request
        if err:
            self._model_key = None
            self.model_area.show_message("Can't show %s\n%s" % (os.path.basename(model), err))
            return
        self.model_area.set_model(scene)                       # a new model: old print results go
        self._show_model_info(model, scene)

    def _show_model_info(self, model, scene):
        self.gen_to_print.hide()
        self.gen_status.setText("📦 %s\n%s\n🖱 Drag to turn  ·  right-drag to move  ·  wheel to zoom  ·  "
                                "double-click to reset" % (os.path.basename(model), scene.info))
        set_tone(self.gen_status, "bad" if "TOO BIG" in scene.info else "dim")

    def pick_model(self):
        start = os.path.dirname(self.model_path()) if self.model_path() else d4_paths.MODELS
        p = self.pick_file("Choose a 3D model", start, "3D models (*.stl *.3mf *.obj);;All files (*.*)")
        if p:
            self.model_edit.setText(os.path.normpath(p))
            self.gen_name.setText(core.name_from_model(p))
            self._queue_model_preview()               # same file again: no text change, still show it

    # ---- fit check ---------------------------------------------------------------------------
    def fit_check(self, files=None):
        if not files:
            m = self.model_path()
            if not os.path.isfile(m):
                self.info("Fit check", "Choose a 3D model file first (📂 Browse…).\n\nTo check several parts "
                          "together (for example a box and the boards inside it), use 🧩 Assembly….")
                return
            files = [m]
        args = list(files)
        if len(files) == 1:
            for flag in ("supports", "brim", "scale"):
                if flag in self.param_widgets:
                    args += ["--" + flag, "%g" % self.param_widgets[flag][0].value()]
        args.append("--no-open")
        what = os.path.basename(files[0]) if len(files) == 1 else "%d parts" % len(files)
        self.gen_status.setText("🔍 Fit check of %s running …" % what)
        set_tone(self.gen_status, "dim")
        self.log("Fit check: %s" % ", ".join(os.path.basename(f) for f in files))
        threading.Thread(target=self._fit_worker, args=(args,), daemon=True).start()

    def fit_check_assembly(self):
        start = os.path.dirname(self.model_path()) if self.model_path() else d4_paths.MODELS
        files = self.pick_files("Choose ALL parts of the assembly (exported in their assembled positions)",
                                start, "3D models (*.stl *.3mf *.obj);;All files (*.*)")
        if files:
            self.fit_check([os.path.normpath(f) for f in files])

    def _fit_worker(self, args):
        try:
            code, sout, serr = run_tool("fit_check.py", args, timeout=900)
        except Exception as e:                                 # noqa: BLE001
            code, sout, serr = 1, "", str(e)
        self.events.put(("fit_done", code, sout or "", serr or ""))

    def on_fit_done(self, _code, sout, serr):
        r = core.parse_fit_result(sout, serr)
        self.gen_status.setText(r["text"])
        set_tone(self.gen_status, {"OK": "ok", "WARN": "warn"}.get(r["verdict"], "bad"))
        for ln, tag in r["lines"]:
            self.log(ln, tag)
        if r["report"] and os.path.exists(r["report"]):
            self.open_url(r["report"])

    # ---- generate ----------------------------------------------------------------------------
    def generate(self):
        obj = core.OBJECTS[self.obj_box.currentText()]
        values = {flag: "%g" % sp.value() for flag, (sp, lo, hi) in self.param_widgets.items()}
        args, name, et, em = core.generate_args(obj, values, self.extruder(), self.gen_name.text(),
                                                self.model_path(), OUT,
                                                bool(d4_paths.find_prusaslicer()) if obj.get("model") else True)
        if et:
            self.error(et, em)
            return
        if core.is_reserved_name(name):
            self.error("File name", "'%s' is a name Windows reserves. Choose another name." % name)
            return
        self.gen_btn.setEnabled(False)
        self.gen_to_print.hide()
        self.gen_status.setText("Generating %s.x3g …" % name)
        set_tone(self.gen_status, "dim")
        threading.Thread(target=self._generate_worker, args=(obj["script"], args, name), daemon=True).start()

    def _generate_worker(self, script, args, name):
        path = os.path.join(OUT, name + ".x3g")
        try:
            code, sout, serr = run_tool(script, args)
            if code != 0 or not os.path.exists(path):
                self.events.put(("gen_done", False, name, ((serr or "") + "\n" + (sout or "")).strip()[-900:]))
                return
            ok, ctext = self._run_checker(path)
            prev = os.path.join(PREV, name + ".png")
            rp.render(path, out=prev)
            st = self._stats(path)
            short = "Print time ≈ %s + heat-up   ·   filament R %.0f / L %.0f mm   ·   object height %.1f mm" % (
                core.fmt_min(st["time_s"]), st["fil"][0], st["fil"][1], st["zprint"])
            if not ok:
                short += "\n" + "\n".join(ln for ln in ctext.splitlines() if "cmd" in ln or "RESULT" in ln)[:600]
            try:
                paths = Toolpath(path)                         # print moves for the 3D path view
            except Exception as e:                             # noqa: BLE001 - the picture still works
                paths = None
                self.events.put(("log", "3D print-path view not available: %s" % e))
            self.events.put(("gen_done", ok, name, short, paths))
        except Exception as e:                                 # noqa: BLE001
            self.events.put(("gen_done", False, name, "Error: %s" % e))

    def on_gen_done(self, ok, name, text, paths=None):
        self.gen_btn.setEnabled(True)
        path = os.path.join(OUT, name + ".x3g")
        self._gen_name_done = name
        if ok:
            self.gen_status.setText("✅ %s.x3g ready - safety check passed.\n%s" % (name, text))
            set_tone(self.gen_status, "ok")
            self.gen_to_print.show()
        else:
            self.gen_status.setText("❌ %s: problem.\n%s" % (name, text))
            set_tone(self.gen_status, "bad")
        prev = os.path.join(PREV, name + ".png")
        if paths is not None or os.path.exists(prev):
            # 3D print paths first (turn / zoom / layer slider); 3D model + overview picture stay
            # one click away on the buttons above the preview
            keep_model = bool(core.OBJECTS[self.obj_box.currentText()].get("model"))
            self.model_area.set_result(paths, prev if os.path.exists(prev) else None, keep_model)
        self.log("Generated %s.x3g (%s)" % (name, "check OK" if ok else "CHECK FAILED"), "ok" if ok else "alarm")
        self.refresh_library(select=path)

    def _goto_print_generated(self):
        self.tabs.setCurrentWidget(self.tab_print)
        if self._gen_name_done:
            self.refresh_library(select=os.path.join(OUT, self._gen_name_done + ".x3g"))

    # ======================= PRINT TAB =======================================================
    def _build_print_tab(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(12, 12, 12, 12)
        g.setSpacing(12)
        g.setColumnStretch(0, 3)
        g.setColumnStretch(1, 2)
        o, b = card("Print files (output folder)")
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["File", "Print time", "Filament R / L", "Z homing", "Safety check", "Modified"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setMinimumHeight(150)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 6):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self.on_select_file)
        b.addWidget(self.tree, 1)
        row = QHBoxLayout()
        row.addWidget(button("↻ Refresh", lambda: self.refresh_library()))
        row.addWidget(button("📁 Open folder", lambda: os.startfile(OUT)))
        row.addWidget(button("➕ Add file…", self.add_file))
        row.addWidget(button("🗑 Delete", self.delete_file))
        row.addStretch(1)
        b.addLayout(row)
        g.addWidget(o, 0, 0)
        o, b = card("Selected file")
        self.file_info = QPlainTextEdit("Select a file")      # scrolls, so a long check report never
        self.file_info.setObjectName("fileInfo")              # pushes the Print-job card off screen
        self.file_info.setReadOnly(True)
        self.file_info.setMinimumHeight(110)
        self.file_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        b.addWidget(self.file_info)
        g.addWidget(o, 1, 0)
        o, b = card("Preview")
        self.file_preview = ImageView()
        self.file_preview.setMinimumHeight(150)
        b.addWidget(self.file_preview, 1)
        g.addWidget(o, 0, 1)
        o, b = card("Print job")
        self.print_btn = self._ctl(button("▶  Print selected file", self.start_print, kind="filled"))
        self.print_btn.setMinimumHeight(40)
        b.addWidget(self.print_btn)
        row = QHBoxLayout()
        row.addWidget(self._ctl(button("⏸ Pause / Resume", lambda: self.worker.submit("pause"))))
        row.addWidget(self._ctl(button("✖ Cancel print", self.cancel_print)))
        b.addLayout(row)
        self.job_name = label("No print running", name="jobTitle", wrap=True)
        b.addWidget(self.job_name)
        self.prog = QProgressBar()
        self.prog.setObjectName("jobBar")
        self.prog.setTextVisible(False)
        self.prog.setRange(0, 1000)
        b.addWidget(self.prog)
        grid = QGridLayout()
        self.job_vals = {}
        for i, (k, lab) in enumerate((("pct", "Done"), ("elapsed", "Elapsed"), ("left", "Time left"),
                                      ("z", "Height (Z)"), ("fil", "Filament used"), ("noz", "Nozzle"))):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(label(lab, tone="dim"))
            v = label("—", name="value")
            cell.addWidget(v)
            grid.addLayout(cell, i // 3, i % 3)
            self.job_vals[k] = v
        b.addLayout(grid)
        g.addWidget(o, 1, 1)
        g.setRowStretch(0, 1)
        return page

    # ---- library ---------------------------------------------------------------------------
    def _stats(self, path):
        mt = os.path.getmtime(path)
        c = self._stats_cache.get(path)
        if c and c[0] == mt:
            return c[1]
        with open(path, "rb") as fh:
            st = s3g.x3g_stats(s3g.split_x3g(fh.read()))
        self._stats_cache[path] = (mt, st)
        return st

    def selected_path(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it and it.isSelected() else None

    def refresh_library(self, select=None):
        cur = select or self.selected_path()
        self.tree.blockSignals(True)
        self.tree.clear()
        files = [os.path.join(OUT, f) for f in os.listdir(OUT) if f.lower().endswith(".x3g")
                 and not f.startswith("_")] if os.path.isdir(OUT) else []
        files.sort(key=os.path.getmtime, reverse=True)
        target = None
        for p in files:
            try:
                st = self._stats(p)
                cc = self._check_cache.get(p)
                check = ("✅ OK" if cc[1] else "❌ FAIL") if cc and cc[0] == os.path.getmtime(p) else "…"
                zh = {"slow": "slow ✓", "fast": "FAST ⚠", None: "none"}[st["z_home"]]
                vals = [os.path.basename(p), core.fmt_min(st["time_s"]), "%.0f / %.0f mm" % tuple(st["fil"]), zh,
                        check, time.strftime("%d %b %H:%M", time.localtime(os.path.getmtime(p)))]
            except Exception:                                  # noqa: BLE001 - unreadable file
                vals = [os.path.basename(p), "?", "?", "?", "unreadable", ""]
            it = QTreeWidgetItem(vals)
            it.setData(0, Qt.ItemDataRole.UserRole, p)
            for c in range(1, 6):
                it.setTextAlignment(c, Qt.AlignmentFlag.AlignCenter)
            self.tree.addTopLevelItem(it)
            if cur and os.path.normcase(p) == os.path.normcase(cur):
                target = it
        self.tree.blockSignals(False)
        if target is not None:
            self.tree.setCurrentItem(target)
            target.setSelected(True)
            self.tree.scrollToItem(target)

    def _item_of(self, path):
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if os.path.normcase(it.data(0, Qt.ItemDataRole.UserRole)) == os.path.normcase(path):
                return it
        return None

    def _run_checker(self, path):
        code, sout, serr = run_tool("check_x3g.py", [path], timeout=300)
        ok, text = core.check_summary(sout)
        self._check_cache[path] = (os.path.getmtime(path), ok, text)
        return ok, text

    def on_select_file(self):
        path = self.selected_path()
        if not path or not os.path.exists(path):
            return
        try:
            st = self._stats(path)
        except Exception as e:                                 # noqa: BLE001
            self.file_info.setPlainText("Cannot read %s: %s" % (os.path.basename(path), e))
            return
        self._show_file_info(path, st)
        prev = os.path.join(PREV, os.path.splitext(os.path.basename(path))[0] + ".png")
        stale = not os.path.exists(prev) or os.path.getmtime(prev) < os.path.getmtime(path)
        cc = self._check_cache.get(path)
        need_check = not (cc and cc[0] == os.path.getmtime(path))
        if stale or need_check:
            self.file_preview.set_text("Rendering preview / checking …")
            threading.Thread(target=self._prepare_file_worker, args=(path, prev, stale, need_check),
                             daemon=True).start()
        else:
            self.file_preview.set_image(prev)

    def _prepare_file_worker(self, path, prev, stale, need_check):
        try:
            if stale:
                rp.render(path, out=prev)
            if need_check:
                self._run_checker(path)
        except Exception as e:                                 # noqa: BLE001
            self.events.put(("log", "Preview/check failed for %s: %s" % (os.path.basename(path), e)))
        self.events.put(("file_ready", path, prev))

    def on_file_ready(self, path, prev):
        it = self._item_of(path)
        cc = self._check_cache.get(path)
        if it is not None and cc:
            it.setText(4, "✅ OK" if cc[1] else "❌ FAIL")
        if self.selected_path() and os.path.normcase(self.selected_path()) == os.path.normcase(path):
            self._show_file_info(path, self._stats(path))
            if os.path.exists(prev):
                self.file_preview.set_image(prev)

    def _show_file_info(self, path, st):
        cc = self._check_cache.get(path)
        self.file_info.setPlainText("\n".join(core.file_info_lines(path, st, cc[2] if cc else None)))

    def add_file(self):
        p = self.pick_file("Add a print file", "", "x3g print files (*.x3g)")
        if p:
            dst = os.path.join(OUT, os.path.basename(p))
            if os.path.abspath(p) != os.path.abspath(dst):
                shutil.copy(p, dst)
            self.refresh_library(select=dst)

    def delete_file(self):
        p = self.selected_path()
        if not p:
            return
        if self.ask("Delete", "Delete %s ?" % os.path.basename(p)):
            for f in (p, os.path.splitext(p)[0] + ".gcode",
                      os.path.join(PREV, os.path.splitext(os.path.basename(p))[0] + ".png")):
                try:
                    os.remove(f)
                except OSError:
                    pass
            self.refresh_library()

    # ---- printing ------------------------------------------------------------------------
    def start_print(self):
        path = self.selected_path()
        if not path:
            self.info("Print", "Select a file in the list first.")
            return
        if not self.connected:
            self.error("Print", "The printer is not connected.")
            return
        st = self._stats(path)
        cc = self._check_cache.get(path)
        if not (cc and cc[0] == os.path.getmtime(path)):
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self._run_checker(path)
            finally:
                QApplication.restoreOverrideCursor()
            cc = self._check_cache.get(path)
        for kind, title, msg in core.print_gate(st, cc[1], cc[2], self.connected, self.bed_ok.isChecked(),
                                                self._last_temps.get("bed")):
            if kind == "block":
                self.error(title, msg)
                return
            if not self.ask(title, msg):
                return
        if not self.checklist(path, st):
            return
        self.print_stats, self.printing, self.heat_phase = st, True, None
        self.job_file = os.path.basename(path)
        self._set_prog(0.0, done=False)
        self.job_name.setText("⏳ Homing, then heating - " + self.job_file)
        for v in self.job_vals.values():
            v.setText("—")
        self.worker.submit("print", path)
        self.log("Print started: %s" % self.job_file, "ok")

    def cancel_print(self):
        if self.printing and self.ask("Cancel print", "Stop the print now? Motion stops and heaters switch off."):
            self.worker.submit("cancel")

    def _set_prog(self, frac, done=False):
        self.prog.setValue(int(round(1000 * max(0.0, min(1.0, frac)))))
        want = "true" if done else "false"
        if self.prog.property("done") != want:
            self.prog.setProperty("done", want)
            restyle(self.prog)

    # ======================= ACTIONS (printer tab) ===========================================
    def set_controls(self, on):
        for b in self._controls:
            b.setEnabled(on)

    NO_PORT_TEXT = "No printer found - switch it on / check the USB cable"

    def refresh_ports(self, autoconnect=False, select=None):
        ports = s3g.find_ports()
        if select and select not in [p[0] for p in ports]:      # connected port must always be listed
            ports = [(select, "%s  (Duplicator / MakerBot)" % select, True)] + ports
        self._ports = ports
        self.port_box.blockSignals(True)
        self.port_box.clear()
        self.port_box.addItems([p[1] for p in ports] or [self.NO_PORT_TEXT])
        if select:
            self.port_box.setCurrentIndex([p[0] for p in ports].index(select))
        self.port_box.blockSignals(False)
        set_tone(self.port_box, "" if ports else "dim")
        if ports and autoconnect and ports[0][2]:
            self.toggle_connect()

    def watch_ports(self):
        if self.connected or self.user_disconnected or time.time() < self._connecting_until:
            return
        ports = s3g.find_ports()
        if [p[0] for p in ports] != [p[0] for p in self._ports]:
            self.refresh_ports()
        printer = next((p for p in ports if p[2]), None)
        if printer:
            self._connecting_until = time.time() + 8
            self.log("Printer found on %s - connecting…" % printer[0])
            self.worker.submit("connect", printer[0])

    def toggle_connect(self):
        if self.connected:
            self.user_disconnected = True
            self.worker.submit("disconnect")
            return
        self.user_disconnected = False
        idx = self.port_box.currentIndex()
        if idx < 0 or not self._ports:
            self.refresh_ports()
            return
        port = self._ports[min(idx, len(self._ports) - 1)][0]
        self._connecting_until = time.time() + 8
        self.log("Connecting to %s…" % port)
        self.worker.submit("connect", port)

    def estop(self):
        self.worker.emergency_stop()
        self.log("EMERGENCY STOP requested", "alarm")

    def set_heater(self, key, value=None):
        c = self.t_entry[key].value() if value is None else value
        if key == "bed":
            ok, v, title, msg = core.bed_heat_decision(c, self.bed_ok.isChecked(), self._last_temps.get("bed"))
            if not ok:
                self.warn(title, msg)
                return
            if msg:
                self.log(msg)
            self.worker.submit("set_bed", v)
        else:
            v = core.nozzle_value(c)
            if v is not None:
                self.worker.submit("set_temp", 0 if key == "r" else 1, v)

    def preset(self, c):
        for key in ("r", "l"):
            self.t_entry[key].setValue(c)
            self.set_heater(key)

    def jog(self, axis, sign):
        self.worker.submit("jog", axis, self.step_mm() * sign, 8.0 if axis == 2 else 30.0)

    def extrude(self, tool, sign):
        mm, question = core.extrude_decision(self._last_temps.get(("r", "l")[tool]), float(self.e_amt.value()))
        if question and not self.ask("Nozzle is cold", ("Right", "Left")[tool] + " nozzle: " + question):
            return
        self.worker.submit("extrude", tool, sign * mm)

    def filament(self, tool, action):
        temp = core.filament_temp(self.fil_temp.value())
        side = ("RIGHT", "LEFT")[tool]
        if action == "load":
            text = ("LOAD filament - %s extruder\n\n1. Nozzle heats to %d °C.\n2. The extruder turns slowly for "
                    "about 40 s.\n3. Push the filament (cut straight) into the top of the extruder until the gears "
                    "grab it.\n4. When plastic comes out, press '■ Stop filament'.\n\nStart?" % (side, temp))
        else:
            text = ("UNLOAD filament - %s extruder\n\n1. Nozzle heats to %d °C.\n2. Pushes 8 mm, then pulls back "
                    "100 mm.\n3. When the motor stops, pull the filament out.\n\nStart?" % (side, temp))
        if self.ask_ok(action.capitalize() + " filament", text):
            self.worker.submit(action, tool, temp, self.keep_hot.isChecked())

    def home_z(self):
        if self.ask_ok("Home Z", "The bed moves UP until it presses the Z switch.\nBe ready to press EMERGENCY STOP (Esc)."):
            self.worker.submit("home_z")

    def home_all(self):
        if self.ask_ok("Home all", "Head goes to back-right, then the bed moves UP to the Z switch.\n"
                       "Be ready to press EMERGENCY STOP (Esc)."):
            self.worker.submit("home_all")

    def motor_test(self):
        if self.ask_ok("Motor test", "Moves X ±20 mm, Y ±20 mm, bed ±10 mm, then each extruder ±2 mm.\n"
                       "Heaters are switched off. Keep hands clear."):
            self.worker.submit("motor_test")

    # ======================= EVENTS ==========================================================
    def pump(self):
        for _ in range(200):                                   # never block the window for long
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                getattr(self, "on_" + ev[0])(*ev[1:])
            except Exception:                                  # noqa: BLE001 - one bad event must not stop the rest
                _crash_log("event %r: %s" % (ev[0], traceback.format_exc()))
                self.log("ERROR handling '%s' (details in output\\crash_log.txt)" % ev[0], "alarm")

    def on_log(self, msg):
        self.log(msg, "alarm" if msg.startswith(("ERROR", "WARNING")) else None)

    def on_alarm(self, msg):
        self.log(msg, "alarm")
        self.error("Printer alarm", msg)

    def on_connected(self, port, fw):
        self.connected = True
        # the printer link can reconnect by itself: show the port it really uses (the list was
        # only refreshed while disconnected, so it could still say "no printer" when connected)
        self.refresh_ports(select=port)
        self.conn_btn.setText("Disconnect")
        self.conn_lbl.setText("● Connected  %s  (%s)" % (port, fw))
        set_tone(self.conn_lbl, "ok")
        self.set_controls(True)
        self.log("Connected to %s, firmware %s" % (port, fw), "ok")

    def on_disconnected(self, reason):
        was = self.connected
        self.connected = False
        self.conn_btn.setText("Connect")
        self.conn_lbl.setText("● Disconnected")
        set_tone(self.conn_lbl, "bad" if was else "dim")
        self.board_lbl.setText("")
        self.set_controls(False)
        self.refresh_ports()                                      # list what is plugged in now
        self.log(reason, "alarm" if was else None)

    def on_progress(self, i, n, elapsed):
        frac, left = core.progress(self.print_stats, i, n)
        self._set_prog(frac)
        self.job_vals["pct"].setText("%d %%" % (100 * frac))
        self.job_vals["elapsed"].setText(core.fmt_min(elapsed))
        self.job_vals["left"].setText(core.fmt_min(left) if left is not None else "—")

    def on_phase(self, kind, tool):
        if kind == "heat":
            self.heat_phase = tool
            self._show_heat()
            self.log("Heating the %s - printing starts when it is hot"
                     % ("bed" if tool == "bed" else "right nozzle" if tool == 0 else "left nozzle"))
        else:
            if self.heat_phase is not None:
                self.log("Hot - printing", "ok")
            self.heat_phase = None
            self.job_name.setText("▶ Printing - " + self.job_file)

    def _show_heat(self):
        tool = self.heat_phase
        if tool is None or not self.printing:
            return
        key = "bed" if tool == "bed" else "r" if tool == 0 else "l"
        cur, tgt = self._last_temps.get(key), self._last_temps.get(key + "_t")
        what = "bed" if tool == "bed" else ("right" if tool == 0 else "left") + " nozzle"
        temp = " %s° → %s°" % (cur, tgt) if cur is not None and tgt else ""
        self.job_name.setText("🔥 Heating %s%s - print starts when hot" % (what, temp))

    def on_print_done(self, ok, msg):
        self.printing = False
        self.heat_phase = None
        self.job_name.setText(("✅ " if ok else "⚠ ") + msg)
        if ok:
            self._set_prog(1.0, done=True)
            self.job_vals["pct"].setText("100 %")
            self.job_vals["left"].setText("0:00")
        self.log(msg, "ok" if ok else "alarm")
        if not ok:
            self.warn("Print stopped", msg)

    def on_status(self, s):
        t = s["t"]
        self._last_temps = t
        for key in ("r", "l", "bed"):
            v, tg = t.get(key), t.get(key + "_t")
            self.t_lbl[key].setText("%s°" % (v if v is not None else "---"))
            text, heating = core.temp_state(v, tg)
            self.t_tgt[key].setText(text)
            set_tone(self.t_tgt[key], "warn" if heating else "dim")
            top = max(tg or 0, 250 if key != "bed" else 110)
            self.t_bar[key].setValue(int(1000 * max(0, min(1, (v or 0) / top))))
        now = time.time()
        self.hist.append((now, t.get("r"), t.get("l"), t.get("bed"), t.get("r_t"), t.get("l_t"), t.get("bed_t")))
        while self.hist and now - self.hist[0][0] > core.CHART_SPAN_S:
            self.hist.popleft()
        self.chart.update()
        es = s["es"]
        for bit in self.sw:
            self._set_switch(bit, bool(es >> bit & 1))
        if self.es_last is not None and es != self.es_last:
            self.es_changes.append(now)
        self.es_last = es
        while self.es_changes and now - self.es_changes[0] > core.SWITCH_FLUTTER_S:
            self.es_changes.popleft()
        self.sw_warn.setText("⚠ switch signal changing a lot - loose wire?"
                             if len(self.es_changes) > core.SWITCH_FLUTTER_N else "")
        p = s["pos"]
        self._last_pos = p
        self.pos_lbl.setText("X %.2f   Y %.2f   Z %.2f\nRight ext %.1f   Left ext %.1f  (mm)" % tuple(p))
        self.homed_lbl.setText("Homed" if s["homed"] else "Not homed - positions relative to power-on")
        set_tone(self.homed_lbl, "ok" if s["homed"] else "dim")
        text, bad = core.board_text(s["board"], s3g.BOARD_FLAGS)
        self.board_lbl.setText(text)
        set_tone(self.board_lbl, "warn" if bad else "dim")
        self.status_temps.setText("R %s°C   L %s°C   bed %s°C   Z %.2f" % (t.get("r"), t.get("l"), t.get("bed"), p[2]))
        if self.printing:
            self._show_heat()
            self.job_vals["z"].setText("%.2f mm" % p[2])
            self.job_vals["fil"].setText("R %.0f / L %.0f mm" % (max(0, p[3]), max(0, p[4])))
            self.job_vals["noz"].setText("R %s° / L %s°" % (t.get("r"), t.get("l")))

    # ======================= MISC ============================================================
    def log(self, msg, tag=None):
        line = time.strftime("%H:%M:%S  ") + msg
        style = {"alarm": "color:%s;font-weight:bold;" % COL["danger"], "ok": "color:%s;" % COL["ok"]}.get(tag, "")
        # always rich text (a <span>), so spacing is kept and nothing in the message is read as markup
        self.logbox.append('<span style="white-space:pre-wrap;%s">%s</span>' % (style, html.escape(line)))
        self.status_lbl.setText(msg[:140])
        set_tone(self.status_lbl, "bad" if tag == "alarm" else "")
        try:
            with open(LOGFILE, "a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d ") + line + "\n")
        except OSError:
            pass

    def apply_theme(self, choice):
        """Live theme switch: Qt repaints every widget at once - no restart, nothing to remember."""
        global THEME, THEME_CHOICE
        if choice not in core.THEME_CHOICES:
            return
        THEME_CHOICE = choice
        try:
            core.save_settings(theme=choice)
        except OSError:
            pass
        THEME = core.resolve_theme(choice)
        COL.clear()
        COL.update(core.PALETTES[THEME])
        if self.theme_box.currentText() != choice:            # switched from code: keep the box in step
            self.theme_box.blockSignals(True)
            self.theme_box.setCurrentText(choice)
            self.theme_box.blockSignals(False)
        apply_app_theme(QApplication.instance())
        self.chart.update()
        for d in self.findChildren(Dot):
            d.update()
        self.model_area.theme_changed()
        self.log("Theme set to %s" % choice)

    @staticmethod
    def licence_folder():
        """Folder with LICENSE, THIRD_PARTY_NOTICES.md and licenses/. From source: the project. In the
        .exe the texts are packed inside; they are copied once to the data folder so they can be read."""
        if not d4_paths.FROZEN:
            return d4_paths.PROJECT
        dst = os.path.join(d4_paths.DATA, "licences")
        try:
            if not os.path.exists(os.path.join(dst, "LICENSE")):
                os.makedirs(dst, exist_ok=True)
                for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                    shutil.copyfile(os.path.join(d4_paths.BUNDLE, name), os.path.join(dst, name))
                shutil.copytree(os.path.join(d4_paths.BUNDLE, "licenses"), os.path.join(dst, "licenses"),
                                dirs_exist_ok=True)
        except OSError:
            pass
        return dst

    def show_about(self):
        lic = os.path.join(self.licence_folder(), "THIRD_PARTY_NOTICES.md")
        self.info("About", "Duplicator 4 Studio\n\nDeveloped by ARUN\n%s\n\n"
                  "Free software under the GNU General Public License v3.0 - WITHOUT ANY WARRANTY.\n"
                  "Never leave a printer unattended.\n\n"
                  "Uses: Qt for Python / PySide6 (LGPL-3.0), Python (PSF), NumPy (BSD), Manifold (Apache-2.0), "
                  "Pillow (MIT-CMU), pySerial (BSD), three.js (MIT).\n"
                  "Slicing engine: PrusaSlicer (AGPL-3.0), a separate program.\n\n"
                  "Licence texts: LICENSE, THIRD_PARTY_NOTICES.md and the licenses folder\n%s\n\n"
                  "Not affiliated with Wanhao or MakerBot." % (__copyright__, os.path.dirname(os.path.abspath(lic))))

    # ---- remember settings between sessions ------------------------------------------------
    def _collect_ui(self):
        self._remember_params()
        tab = {0: "printer", 1: "prepare", 2: "print"}.get(self.tabs.currentIndex(), "printer")
        return {
            "tab": tab,
            "qt_geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            "temps": {k: str(self.t_entry[k].value()) for k in ("r", "l", "bed")},
            "step": self.step_mm(),
            "move_mm": str(self.e_amt.value()),
            "load_temp": str(self.fil_temp.value()),
            "keep_hot": self.keep_hot.isChecked(),
            "object": self.obj_box.currentText(),
            "obj_params": self._obj_params,
            "last_file": self.selected_path() or self.ui.get("last_file"),
        }

    def save_ui(self):
        try:
            self.ui = self._collect_ui()
            core.save_settings(ui=self.ui)
        except (OSError, ValueError, TypeError):
            pass

    def _restore_ui(self):
        u = self.ui
        try:
            g = u.get("qt_geometry")
            if g:
                self.restoreGeometry(QByteArray.fromBase64(g.encode("ascii")))
            for key in ("r", "l", "bed"):
                v = core.parse_number(u.get("temps", {}).get(key))
                if v is not None:
                    self.t_entry[key].setValue(int(v))
            for b in self.step_group.buttons():
                if abs(float(b.property("mm")) - float(u.get("step", 10))) < 1e-9:
                    b.setChecked(True)
            for sp, k in ((self.e_amt, "move_mm"), (self.fil_temp, "load_temp")):
                v = core.parse_number(u.get(k))
                if v is not None:
                    sp.setValue(int(v))
            self.keep_hot.setChecked(bool(u.get("keep_hot", False)))
            if u.get("object") in core.OBJECTS and u["object"] != self.obj_box.currentText():
                self.obj_box.blockSignals(True)
                self.obj_box.setCurrentText(u["object"])
                self.obj_box.blockSignals(False)
                self._params_for = None                   # nothing to remember from the default object
                self._build_params()
            idx = {"printer": 0, "prepare": 1, "print": 2}.get(u.get("tab"))
            if idx is not None:
                self.tabs.setCurrentIndex(idx)
        except (ValueError, TypeError) as e:
            self.log("Could not restore some saved settings: %s" % e)

    # ---- closing -----------------------------------------------------------------------------
    def closeEvent(self, e):
        if self.printing and not self.ask("Print running", "A USB print is running. Closing stops sending and the "
                                          "print will stall.\nStop the print and close?"):
            e.ignore()
            return
        if self.printing:
            self.worker.emergency_stop()
            time.sleep(0.5)
        self.save_ui()
        for t in self.timers:
            t.stop()
        self.worker.quit.set()
        e.accept()


# =============================================================================================
# App start, crash log, self-test
# =============================================================================================
def _crash_log(text):
    try:
        with open(os.path.join(d4_paths.OUT, "crash_log.txt"), "a", encoding="utf-8") as fh:
            fh.write(time.strftime("\n==== %Y-%m-%d %H:%M:%S ====\n") + text)
    except OSError:
        pass


def apply_app_theme(app):
    app.setPalette(make_palette(COL))
    app.setStyleSheet(stylesheet(COL))


def make_app(argv=None):
    app = QApplication.instance()
    if app is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        QSurfaceFormat.setDefaultFormat(fmt)
        app = QApplication(argv or sys.argv)
        app.setStyle("Fusion")
        app.setApplicationName("Duplicator 4 Studio")
        # one font everywhere: without this, the text INSIDE number boxes and drop-downs (e.g.
        # "printer off?") used Qt's small fallback font while the labels around them used Segoe UI
        f = QFont("Segoe UI", 10)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        f.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
        app.setFont(f)
    apply_app_theme(app)
    return app


def shutdown(app, w, code):
    """Leave the program cleanly. The printer thread first releases the COM port; then every
    window and the OpenGL context are destroyed while Qt is still running; then the process ends
    at once (background tool threads, e.g. a fit check, are not waited for).
    Ending with Qt objects still alive crashed (access violation) inside the graphics driver."""
    try:
        w.worker.quit.set()
        w.worker.join(3.0)
    except Exception:                                      # noqa: BLE001
        pass
    try:
        for t in getattr(w, "timers", []):
            t.stop()
        w.hide()
        w.deleteLater()
        app.processEvents()
        app.sendPostedEvents(None, 0)                      # runs the deleteLater: GL context freed here
        app.processEvents()
        import shiboken6
        shiboken6.delete(app)                              # QApplication destructor while Python is intact
    except Exception:                                      # noqa: BLE001
        pass
    for fh in (sys.stdout, sys.stderr):
        try:
            fh.flush()
        except Exception:                                  # noqa: BLE001
            pass
    os._exit(code)


def selftest():
    """Duplicator4Studio.exe --selftest : bundled tools + the window itself, writes output/selftest.txt."""
    import tempfile
    lines = ["Duplicator 4 Studio self-test  (frozen=%s, Qt window)" % d4_paths.FROZEN,
             "data folder : %s" % d4_paths.DATA,
             "slicer      : %s" % d4_paths.find_prusaslicer()]
    ok_all = True

    def rec(name, ok, msg=""):
        nonlocal ok_all
        ok_all &= bool(ok)
        lines.append("%-18s %s  %s" % (name, "PASS" if ok else "FAIL", "" if ok else str(msg)[:160]))

    with tempfile.TemporaryDirectory() as tmp:
        tests = [("make_left_demo.py", ["--out", tmp], "DEMO_LEFT"),
                 ("make_vase.py", ["--out", tmp, "--name", "ST_VASE", "--height", "6"], "ST_VASE")]
        model = os.path.join(d4_paths.DATA, "models", "test_nut.stl")
        if os.path.exists(model) and d4_paths.find_prusaslicer():
            tests.append(("slice_model.py", ["--out", tmp, "--name", "ST_NUT", "--model", model], "ST_NUT"))
        for script, args, name in tests:
            code, sout, serr = run_tool(script, args)
            x3g = os.path.join(tmp, name + ".x3g")
            ccode, cout, _ = run_tool("check_x3g.py", [x3g]) if os.path.exists(x3g) else (1, "", "")
            rec(script, code == 0 and "RESULT        : OK" in cout,
                (serr.strip() or sout.strip().splitlines()[-1:] or [""])[-1])
        if os.path.exists(model):
            rep = os.path.join(tmp, "fit.html")
            code, sout, serr = run_tool("fit_check.py", [model, "--no-open", "--out", rep])
            rec("fit_check.py", "RESULT:" in sout and os.path.exists(rep) and os.path.getsize(rep) > 100000,
                (serr.strip() or sout.strip())[-160:])
            try:
                import model_preview
                png = os.path.join(tmp, "prev.png")
                info = model_preview.render(model, png)
                rec("model_preview.py", os.path.getsize(png) > 5000 and "mm" in info, info)
            except Exception as e:                             # noqa: BLE001
                rec("model_preview.py", False, e)
        # licence texts must travel with the program (GPL-3.0 + third-party notices)
        lf = MainWindow.licence_folder()
        need = ["LICENSE", "THIRD_PARTY_NOTICES.md", os.path.join("licenses", "LGPL-3.0.txt")]
        missing = [n for n in need if not os.path.exists(os.path.join(lf, n))]
        rec("licence files", not missing, "missing: %s" % ", ".join(missing))
        # the window: build it (no printer), switch theme both ways, show a model
        global LOGFILE
        real_log, LOGFILE = LOGFILE, os.path.join(tmp, "selftest_log.txt")   # keep the real log clean
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

            class _NoPrinter:
                def __init__(self):
                    self.events, self.quit, self.sent = None, threading.Event(), []

                def is_alive(self):
                    return True

                def submit(self, *a):
                    self.sent.append(a)

                def emergency_stop(self):
                    self.sent.append(("estop",))
            app = make_app(["selftest"])
            w = MainWindow(worker=_NoPrinter())
            w.ask = w.ask_ok = lambda *a: False
            w.info = w.warn = w.error = lambda *a: None
            w.resize(1366, 740)
            w.show()
            app.processEvents()
            before = w.centralWidget().palette().color(QPalette.ColorRole.Window).name()
            other = "Dark" if THEME == "light" else "Light"
            keep = THEME_CHOICE
            w.apply_theme(other)
            app.processEvents()
            after = w.centralWidget().palette().color(QPalette.ColorRole.Window).name()
            w.apply_theme(keep)
            rec("window + theme", before != after, "%s -> %s" % (before, after))
            if os.path.exists(model):
                import model_preview
                w.model_area.show_scene(model_preview.Scene(model))
                app.processEvents()
                rec("3D viewer", w.model_area.showing_model(), "viewer not shown")
            w.estop()
            rec("E-STOP wiring", ("estop",) in w.worker.sent, w.worker.sent)
            for t in w.timers:
                t.stop()
            w.hide()
            w.deleteLater()                                    # free everything while Qt still runs
            app.processEvents()
            app.sendPostedEvents(None, 0)
            import shiboken6
            shiboken6.delete(app)
        except Exception:                                      # noqa: BLE001
            rec("window", False, traceback.format_exc().strip().splitlines()[-1])
        finally:
            LOGFILE = real_log
    lines.append("OVERALL: %s" % ("PASS" if ok_all else "FAIL"))
    with open(os.path.join(d4_paths.OUT, "selftest.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return 0 if ok_all else 1


def main():
    if sys.stderr is None:                                     # windowed .exe has no console
        sys.stderr = open(os.path.join(d4_paths.OUT, "stderr_log.txt"), "a", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if "--selftest" in sys.argv:
        code = selftest()
        sys.stdout.flush()
        os._exit(code)
    try:
        import faulthandler
        faulthandler.enable(open(os.path.join(d4_paths.OUT, "crash_log.txt"), "a", encoding="utf-8"))
    except (OSError, RuntimeError, ValueError):
        pass

    def hook(et, ev, tb):
        _crash_log("".join(traceback.format_exception(et, ev, tb)))
        w = getattr(hook, "win", None)
        if w is not None:
            try:
                w.log("ERROR: %s: %s  (details in output\\crash_log.txt)" % (et.__name__, ev), "alarm")
            except Exception:                                  # noqa: BLE001
                pass
    sys.excepthook = hook
    threading.excepthook = lambda a: _crash_log("thread %s: %s" % (
        getattr(a.thread, "name", "?"), "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback))))
    app = make_app()
    try:
        w = MainWindow()
    except Exception:                                          # noqa: BLE001 - startup failure
        tb = traceback.format_exc()
        _crash_log(tb)
        QMessageBox.critical(None, "Duplicator 4 Studio", "The app could not start:\n\n%s\n\nDetails: "
                             "output\\crash_log.txt" % tb.strip().splitlines()[-1])
        os._exit(1)
    hook.win = w
    if w.ui.get("qt_geometry"):
        w.show()
    else:
        w.showMaximized()
    code = app.exec()
    shutdown(app, w, code)


if __name__ == "__main__":
    main()
