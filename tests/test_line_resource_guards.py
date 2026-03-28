from __future__ import annotations

import ast
import time
from pathlib import Path
from types import SimpleNamespace


def _load_line_symbols(*, assignment_names=(), function_names=(), namespace=None):
	module_path = Path(__file__).resolve().parents[1] / "addon" / "appModules" / "line.py"
	source = module_path.read_text(encoding="utf-8")
	module = ast.parse(source)
	ns = {} if namespace is None else dict(namespace)

	for node in module.body:
		if isinstance(node, ast.Assign):
			names = {
				target.id
				for target in node.targets
				if isinstance(target, ast.Name)
			}
			if names & set(assignment_names):
				exec(
					compile(
						ast.Module(body=[node], type_ignores=[]),
						str(module_path),
						"exec",
					),
					ns,
				)
		elif isinstance(node, ast.FunctionDef) and node.name in set(function_names):
			exec(
				compile(
					ast.Module(body=[node], type_ignores=[]),
					str(module_path),
					"exec",
				),
				ns,
			)
	return ns


class _Log:
	def debug(self, *args, **kwargs):
		pass

	def info(self, *args, **kwargs):
		pass

	def debugWarning(self, *args, **kwargs):
		pass


def test_notes_window_context_uses_only_fresh_cache():
	ns = _load_line_symbols(
		assignment_names={
			"_NOTES_WINDOW_KEYWORDS",
			"_NOTES_OCR_KEYWORDS",
			"_NOTES_OCR_CACHE_TTL",
			"_notesWindowDetectionCache",
		},
		function_names={"_isNotesWindowContext"},
		namespace={"log": _Log(), "time": time},
	)
	walker = SimpleNamespace(GetParentElement=lambda _element: None)
	ns["_getForegroundWindowInfo"] = lambda: (101, "line", (0, 0, 1200, 800))

	ns["_notesWindowDetectionCache"] = {
		"key": (101, "line", (0, 0, 1200, 800)),
		"expiresAt": time.monotonic() + 5.0,
		"isNotesWindow": True,
	}
	assert ns["_isNotesWindowContext"](object(), walker) == (True, "line")

	ns["_notesWindowDetectionCache"] = {
		"key": (101, "line", (0, 0, 1200, 800)),
		"expiresAt": time.monotonic() - 1.0,
		"isNotesWindow": True,
	}
	assert ns["_isNotesWindowContext"](object(), walker, allowOcr=False) == (False, "line")


def test_rect_visibility_checks_overlap_with_foreground_window():
	ns = _load_line_symbols(
		function_names={"_rectsIntersect", "_isRectVisibleInForegroundWindow"},
	)
	ns["_getForegroundWindowInfo"] = lambda: (101, "line", (100, 100, 400, 400))

	assert ns["_isRectVisibleInForegroundWindow"](150, 150, 300, 300) is True
	assert ns["_isRectVisibleInForegroundWindow"](450, 450, 500, 500) is False


def test_extract_matched_message_context_menu_labels_ignores_message_body_text():
	known_labels = {"回覆", "複製", "分享", "刪除", "收回"}
	ns = _load_line_symbols(
		function_names={"_extractMatchedMessageContextMenuLabels"},
		namespace={
			"_removeCJKSpaces": lambda text: text.replace(" ", ""),
			"_matchMessageContextMenuLabel": lambda text: text if text in known_labels else None,
		},
	)

	popup_lines, line_matches, matched_labels = ns["_extractMatchedMessageContextMenuLabels"](
		"本次更新新增了訊息右鍵選單\n"
		"天、回覆、複製、收回等重要站點\n"
		"日期：2026 年 3 月 27 日"
	)

	assert popup_lines[1] == "天、回覆、複製、收回等重要站點"
	assert line_matches[1] == ("天、回覆、複製、收回等重要站點", None)
	assert matched_labels == []


def test_extract_matched_message_context_menu_labels_accepts_real_menu_rows():
	known_labels = {"回覆", "複製", "分享", "刪除", "收回"}
	ns = _load_line_symbols(
		function_names={"_extractMatchedMessageContextMenuLabels"},
		namespace={
			"_removeCJKSpaces": lambda text: text.replace(" ", ""),
			"_matchMessageContextMenuLabel": lambda text: text if text in known_labels else None,
		},
	)

	_popup_lines, line_matches, matched_labels = ns["_extractMatchedMessageContextMenuLabels"](
		"回覆\n複製\n分享"
	)

	assert line_matches == [("回覆", "回覆"), ("複製", "複製"), ("分享", "分享")]
	assert matched_labels == ["回覆", "複製", "分享"]


def test_detect_edit_field_label_message_hint_skips_notes_detection():
	class _Rect:
		left = 700
		top = 520
		bottom = 640

	class _Element:
		CurrentName = "輸入訊息"
		CurrentBoundingRectangle = _Rect()

		def GetCurrentPropertyValue(self, _prop):
			return ""

	class _EditElements:
		Length = 1

	class _Parent:
		def FindAll(self, _scope, _condition):
			return _EditElements()

	class _Walker:
		def GetParentElement(self, _element):
			return _Parent()

	class _Client:
		RawViewWalker = _Walker()

		def CreatePropertyCondition(self, *_args):
			return object()

	ns = _load_line_symbols(
		function_names={"_getEditPlaceholder", "_detectEditFieldLabel"},
		namespace={
			"_": lambda text: text,
			"UIAHandler": SimpleNamespace(TreeScope_Children=1),
			"ctypes": SimpleNamespace(
				windll=SimpleNamespace(
					user32=SimpleNamespace(
						GetForegroundWindow=lambda: 101,
						GetWindowRect=lambda _hwnd, rect: None,
					),
				),
				wintypes=SimpleNamespace(RECT=lambda: SimpleNamespace(left=0, top=0, right=1200, bottom=800)),
				byref=lambda value: value,
			),
			"log": _Log(),
		},
	)
	ns["_isNotesWindowContext"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(
		AssertionError("notes detection should not run for message fast-path")
	)

	handler = SimpleNamespace(clientObject=_Client())
	assert ns["_detectEditFieldLabel"](_Element(), handler) == "Message input"


def test_detect_edit_field_label_query_text_skips_notes_ocr():
	seen_allow_ocr = []

	class _Rect:
		left = 120
		top = 130
		bottom = 180

	class _Element:
		CurrentName = ""
		CurrentBoundingRectangle = _Rect()

		def GetCurrentPropertyValue(self, prop_id):
			if prop_id == 30045:
				return "黃淑"
			return ""

	class _EditElements:
		Length = 1

	class _Parent:
		def FindAll(self, _scope, _condition):
			return _EditElements()

	class _Walker:
		def GetParentElement(self, _element):
			return _Parent()

	class _Client:
		RawViewWalker = _Walker()

		def CreatePropertyCondition(self, *_args):
			return object()

	ns = _load_line_symbols(
		function_names={"_getEditPlaceholder", "_detectEditFieldLabel"},
		namespace={
			"_": lambda text: text,
			"UIAHandler": SimpleNamespace(TreeScope_Children=1),
			"ctypes": SimpleNamespace(
				windll=SimpleNamespace(
					user32=SimpleNamespace(
						GetForegroundWindow=lambda: 101,
						GetWindowRect=lambda _hwnd, rect: None,
					),
				),
				wintypes=SimpleNamespace(RECT=lambda: SimpleNamespace(left=0, top=0, right=1200, bottom=800)),
				byref=lambda value: value,
			),
			"log": _Log(),
		},
	)

	def _fake_notes_context(*_args, **kwargs):
		seen_allow_ocr.append(kwargs["allowOcr"])
		return False, "line"

	ns["_isNotesWindowContext"] = _fake_notes_context

	handler = SimpleNamespace(clientObject=_Client())
	assert ns["_detectEditFieldLabel"](_Element(), handler) == "Search chat rooms"
	assert seen_allow_ocr == [False]


def test_schedule_query_invalidates_active_copy_read():
	scheduled = []
	focus_calls = []

	ns = _load_line_symbols(
		assignment_names={"_copyReadRequestId", "_focusQueryRequestId"},
		function_names={"_invalidateActiveCopyRead", "_scheduleQueryAndSpeakUIAFocus"},
		namespace={
			"core": SimpleNamespace(callLater=lambda _delay, callback: scheduled.append(callback)),
		},
	)
	ns["_queryAndSpeakUIAFocus"] = lambda: focus_calls.append("focus")
	ns["_copyReadRequestId"] = 7
	ns["_focusQueryRequestId"] = 0

	ns["_scheduleQueryAndSpeakUIAFocus"](50)

	assert ns["_copyReadRequestId"] == 8
	assert ns["_focusQueryRequestId"] == 1
	assert len(scheduled) == 1

	scheduled[0]()
	assert focus_calls == ["focus"]


def test_copy_read_stale_request_restores_clipboard_without_followup():
	copy_calls = []
	scheduled = []
	fallback_calls = []

	class _Rect:
		left = 100
		top = 200
		right = 400
		bottom = 260

	class _Target:
		CurrentBoundingRectangle = _Rect()

		def GetRuntimeId(self):
			return (1, 2, 3)

	user32 = SimpleNamespace(
		GetForegroundWindow=lambda: 101,
		SetForegroundWindow=lambda _hwnd: None,
		SetCursorPos=lambda _x, _y: None,
		mouse_event=lambda *_args: None,
	)

	ns = _load_line_symbols(
		assignment_names={"_copyReadRequestId", "_copyReadClipboardOwnerId"},
		function_names={"_copyAndReadMessage"},
		namespace={
			"api": SimpleNamespace(
				getClipData=lambda: "orig",
				copyToClip=lambda value: copy_calls.append(value),
			),
			"core": SimpleNamespace(
				callLater=lambda _delay, callback: scheduled.append(callback),
			),
			"ctypes": SimpleNamespace(windll=SimpleNamespace(user32=user32)),
			"time": SimpleNamespace(sleep=lambda _seconds: None),
			"log": _Log(),
			"_getElementRuntimeId": lambda _element: (1, 2, 3),
			"_getFocusedElementRuntimeId": lambda: (1, 2, 3),
			"_ocrReadMessageFallback": lambda _element: fallback_calls.append("fallback"),
		},
	)

	ns["_copyAndReadMessage"](_Target())
	assert copy_calls == [""]
	assert len(scheduled) == 1

	ns["_copyReadRequestId"] += 1
	scheduled[0]()

	assert copy_calls == ["", "orig"]
	assert fallback_calls == []
	assert ns["_copyReadClipboardOwnerId"] == 0
