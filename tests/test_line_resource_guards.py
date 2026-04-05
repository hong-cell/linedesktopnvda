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


def test_extract_recall_dialog_action_labels_handles_modern_dialog_without_matching_body_text():
	ns = _load_line_symbols(
		function_names={
			"_normalizeRecallDialogLine",
			"_matchRecallDialogActionLabel",
			"_extractRecallDialogActionLabels",
		},
		namespace={
			"_removeCJKSpaces": lambda text: text.replace(" ", ""),
		},
	)

	labels = ns["_extractRecallDialogActionLabels"](
		"確定要收回訊息嗎？\n"
		"您可無痕收回此則未讀訊息，對方不會收到任何提醒。\n"
		"依對方使用的LINE版本而定，有可能無法收回訊息。\n"
		"無痕收回 Premium\n"
		"收回\n"
		"關閉"
	)

	assert labels == ["無痕收回", "收回", "取消"]


def test_get_recall_confirmation_prompt_marks_stealth_option_as_premium():
	ns = _load_line_symbols(
		function_names={"_getRecallConfirmationPrompt"},
		namespace={"_": lambda text: text},
	)

	assert ns["_getRecallConfirmationPrompt"]({"收回", "取消"}) == "確認要收回嗎？按 Y 收回，按 N 取消"
	assert (
		ns["_getRecallConfirmationPrompt"](
			{"收回", "取消"},
			isModernDialog=True,
		)
		== "確認要收回嗎？按 Y 收回，按 N 取消"
	)
	assert (
		ns["_getRecallConfirmationPrompt"](
			{"無痕收回", "收回", "取消"},
			isModernDialog=True,
		)
		== "確認要收回嗎？按 Y 收回，按 N 取消，按 P 無痕收回，需要 Premium"
	)


def test_is_modern_recall_dialog_text_accepts_compact_two_button_modern_layout():
	ns = _load_line_symbols(
		function_names={"_isModernRecallDialogText"},
		namespace={"_removeCJKSpaces": lambda text: text.replace(" ", "")},
	)

	assert ns["_isModernRecallDialogText"](
		"確定要收回此訊息嗎 ?\n"
		"收回已讀訊息時, 對方將會收到通知。\n"
		"依對方使用的LINE版本而定, 有可能無法收回訊息。\n"
		"收回\n"
		"關閉",
		["收回", "取消"],
	) is True


def test_is_compact_modern_recall_dialog_requires_two_button_modern_state():
	ns = _load_line_symbols(
		function_names={"_isCompactModernRecallDialog"},
	)

	assert ns["_isCompactModernRecallDialog"](["收回", "取消"], isModernDialog=True) is True
	assert ns["_isCompactModernRecallDialog"](["無痕收回", "收回", "取消"], isModernDialog=True) is False
	assert ns["_isCompactModernRecallDialog"](["收回", "取消"], isModernDialog=False) is False


def test_try_invoke_uia_element_prefers_direct_invoke_without_generated_stubs():
	ns = _load_line_symbols(
		function_names={"_invokeUIAInvokePattern", "_tryInvokeUIAElement"},
	)

	class _Pattern:
		def __init__(self):
			self.invoked = 0

		def Invoke(self):
			self.invoked += 1

	class _Element:
		def __init__(self):
			self.pattern_ids = []
			self.pattern = _Pattern()

		def GetCurrentPattern(self, patternId):
			self.pattern_ids.append(patternId)
			return self.pattern

	element = _Element()
	assert ns["_tryInvokeUIAElement"](element) is True
	assert element.pattern.invoked == 1
	assert element.pattern_ids == [10000]


def test_invoke_uia_invoke_pattern_falls_back_to_query_interface_without_comtypes_gen():
	class _IUnknown:
		pass

	class _Comtypes:
		IUnknown = _IUnknown

		@staticmethod
		def GUID(value):
			return value

		@staticmethod
		def COMMETHOD(*args):
			return ("COMMETHOD", args)

	ns = _load_line_symbols(
		function_names={"_invokeUIAInvokePattern"},
		namespace={
			"comtypes": _Comtypes,
			"ctypes": SimpleNamespace(c_long=object()),
		},
	)

	class _Invokable:
		def __init__(self):
			self.invoked = 0

		def Invoke(self):
			self.invoked += 1

	class _Pattern:
		def __init__(self):
			self.requestedInterface = None
			self.invokable = _Invokable()

		def QueryInterface(self, interfaceType):
			self.requestedInterface = interfaceType
			return self.invokable

	pattern = _Pattern()
	assert ns["_invokeUIAInvokePattern"](pattern) is True
	assert pattern.invokable.invoked == 1
	assert pattern.requestedInterface._iid_ == "{FB377FBE-8EA6-46D5-9C73-6499642D3059}"


def test_extract_ocr_rect_like_unions_word_rects_when_line_rect_is_missing():
	ns = _load_line_symbols(function_names={"_extractOcrRectLike"})

	class _WordRect:
		def __init__(self, left, top, right, bottom):
			self.left = left
			self.top = top
			self.right = right
			self.bottom = bottom

	class _Word:
		def __init__(self, rect):
			self.boundingRect = rect

	class _Line:
		def __init__(self):
			self.words = [
				_Word(_WordRect(480, 620, 520, 650)),
				_Word(_WordRect(522, 618, 560, 648)),
			]

	assert ns["_extractOcrRectLike"](_Line()) == (480, 618, 560, 650)


def test_infer_recall_dialog_targets_by_geometry_recovers_modern_unlabeled_buttons():
	ns = _load_line_symbols(
		function_names={
			"_rectIntersectionArea",
			"_rectIoU",
			"_isCompactModernRecallDialog",
			"_inferRecallDialogTargetsByGeometry",
		},
	)

	candidates = [
		{
			"element": "junk-top",
			"rect": (150, 160, 260, 190),
			"controlType": 50003,
			"hasInvoke": False,
		},
		{
			"element": "stealth",
			"rect": (150, 290, 450, 332),
			"controlType": 50000,
			"hasInvoke": True,
		},
		{
			"element": "recall",
			"rect": (150, 346, 450, 388),
			"controlType": 50000,
			"hasInvoke": True,
		},
		{
			"element": "cancel-text",
			"rect": (238, 420, 362, 446),
			"controlType": 50003,
			"hasInvoke": False,
		},
	]

	inferred = ns["_inferRecallDialogTargetsByGeometry"](
		candidates,
		(100, 120, 500, 500),
		["無痕收回", "收回"],
		isModernDialog=True,
	)

	assert inferred["無痕收回"]["element"] == "stealth"
	assert inferred["收回"]["element"] == "recall"


def test_infer_recall_dialog_targets_by_geometry_recovers_legacy_primary_button():
	ns = _load_line_symbols(
		function_names={
			"_rectIntersectionArea",
			"_rectIoU",
			"_isCompactModernRecallDialog",
			"_inferRecallDialogTargetsByGeometry",
		},
	)

	candidates = [
		{
			"element": "body",
			"rect": (140, 180, 430, 220),
			"controlType": 50003,
			"hasInvoke": False,
		},
		{
			"element": "recall",
			"rect": (150, 320, 450, 364),
			"controlType": 50000,
			"hasInvoke": True,
		},
	]

	inferred = ns["_inferRecallDialogTargetsByGeometry"](
		candidates,
		(100, 120, 500, 500),
		["收回", "取消"],
		isModernDialog=False,
	)

	assert inferred["收回"]["element"] == "recall"


def test_infer_recall_dialog_targets_by_geometry_prefers_compact_modern_button_zone():
	ns = _load_line_symbols(
		function_names={
			"_rectIntersectionArea",
			"_rectIoU",
			"_isCompactModernRecallDialog",
			"_inferRecallDialogTargetsByGeometry",
		},
	)

	candidates = [
		{
			"element": "topCard",
			"rect": (150, 260, 450, 304),
			"controlType": 50000,
			"hasInvoke": True,
		},
		{
			"element": "recallButton",
			"rect": (150, 352, 450, 404),
			"controlType": 50000,
			"hasInvoke": True,
		},
	]

	inferred = ns["_inferRecallDialogTargetsByGeometry"](
		candidates,
		(100, 120, 500, 560),
		["收回", "取消"],
		isModernDialog=True,
	)

	assert inferred["收回"]["element"] == "recallButton"


def test_get_recall_dialog_fallback_click_point_covers_legacy_and_modern_layouts():
	ns = _load_line_symbols(
		function_names={
			"_isCompactModernRecallDialog",
			"_getRecallDialogFallbackClickPoint",
		},
	)

	assert ns["_getRecallDialogFallbackClickPoint"]("收回", (100, 200, 500, 600), False) == (300, 432)
	assert ns["_getRecallDialogFallbackClickPoint"]("取消", (100, 200, 500, 600), False) is None
	assert ns["_getRecallDialogFallbackClickPoint"]("無痕收回", (100, 200, 500, 600), True) == (300, 396)
	assert ns["_getRecallDialogFallbackClickPoint"](
		"收回",
		(100, 200, 500, 600),
		True,
		["收回", "取消"],
	) == (300, 456)
	assert ns["_getRecallDialogFallbackClickPoint"]("取消", (100, 200, 500, 600), True) is None


def test_extract_recall_dialog_action_click_points_uses_ocr_label_centers():
	ns = _load_line_symbols(
		function_names={
			"_normalizeRecallDialogLine",
			"_matchRecallDialogActionLabel",
			"_rectsIntersect",
			"_extractRecallDialogActionClickPoints",
		},
		namespace={
			"_removeCJKSpaces": lambda text: text.replace(" ", ""),
		},
	)

	points = ns["_extractRecallDialogActionClickPoints"](
		[
			{"text": "收回訊息。", "rect": (180, 260, 300, 292)},
			{"text": "收回", "rect": (470, 618, 550, 648)},
			{"text": "關閉", "rect": (472, 676, 548, 706)},
		],
		(320, 220, 700, 760),
	)

	assert points == {
		"收回": {
			"clickPoint": (510, 633),
			"rect": (470, 618, 550, 648),
		},
		"取消": {
			"clickPoint": (510, 691),
			"rect": (472, 676, 548, 706),
		},
	}


def test_begin_recall_confirmation_binds_y_n_p_shortcuts():
	module_path = Path(__file__).resolve().parents[1] / "addon" / "appModules" / "line.py"
	source = module_path.read_text(encoding="utf-8")
	module = ast.parse(source)
	app_module = next(
		node
		for node in module.body
		if isinstance(node, ast.ClassDef) and node.name == "AppModule"
	)
	begin_method = next(
		node
		for node in app_module.body
		if isinstance(node, ast.FunctionDef) and node.name == "_beginRecallConfirmation"
	)

	bind_calls = set()
	for node in ast.walk(begin_method):
		if not (
			isinstance(node, ast.Call)
			and isinstance(node.func, ast.Attribute)
			and node.func.attr == "bindGesture"
			and len(node.args) >= 2
		):
			continue
		first_arg, second_arg = node.args[:2]
		if all(
			isinstance(arg, ast.Constant) and isinstance(arg.value, str)
			for arg in (first_arg, second_arg)
		):
			bind_calls.add((first_arg.value, second_arg.value))

	assert ("kb:y", "confirmRecall") in bind_calls
	assert ("kb:n", "cancelRecall") in bind_calls
	assert ("kb:p", "stealthRecall") in bind_calls


def test_end_recall_confirmation_defers_user_feedback_until_post_click_verification():
	module_path = Path(__file__).resolve().parents[1] / "addon" / "appModules" / "line.py"
	source = module_path.read_text(encoding="utf-8")
	module = ast.parse(source)
	app_module = next(
		node
		for node in module.body
		if isinstance(node, ast.ClassDef) and node.name == "AppModule"
	)
	end_method = next(
		node
		for node in app_module.body
		if isinstance(node, ast.FunctionDef) and node.name == "_endRecallConfirmation"
	)

	calls = set()
	for node in ast.walk(end_method):
		if not (
			isinstance(node, ast.Call)
			and isinstance(node.func, ast.Attribute)
			and isinstance(node.func.value, ast.Name)
			and node.func.value.id == "self"
		):
			continue
		calls.add(node.func.attr)

	assert "_performRecallConfirmationAction" in calls
	assert "_scheduleRecallCompletionAnnouncement" in calls
	assert "_clearRecallConfirmationBindings" not in calls


def test_perform_recall_confirmation_action_prefers_ocr_click_point_for_legacy_recall():
	module_path = Path(__file__).resolve().parents[1] / "addon" / "appModules" / "line.py"
	source = module_path.read_text(encoding="utf-8")
	module = ast.parse(source)
	app_module = next(
		node
		for node in module.body
		if isinstance(node, ast.ClassDef) and node.name == "AppModule"
	)
	method = next(
		node
		for node in app_module.body
		if isinstance(node, ast.FunctionDef) and node.name == "_performRecallConfirmationAction"
	)
	compact_helper = next(
		node
		for node in module.body
		if isinstance(node, ast.FunctionDef) and node.name == "_isCompactModernRecallDialog"
	)
	ns = {
		"log": _Log(),
		"_getRecallDialogFallbackClickPoint": lambda *args, **kwargs: None,
		"_": lambda text: text,
	}
	exec(
		compile(
			ast.Module(body=[compact_helper, method], type_ignores=[]),
			str(module_path),
			"exec",
		),
		ns,
	)
	perform = ns["_performRecallConfirmationAction"]
	clicks = []

	class _Self:
		def _refreshRecallConfirmationState(self):
			return {
				"targets": {
					"收回": {
						"element": object(),
						"rect": (100, 200, 300, 320),
						"clickPoint": (210, 278),
					},
				},
				"isModernDialog": False,
				"hwnd": 123,
				"dialogRect": (50, 50, 350, 350),
			}

		def _invokeElement(self, *args, **kwargs):
			raise AssertionError("legacy recall should click the OCR hit before invoking UIA")

		def _clickAtPosition(self, *args, **kwargs):
			clicks.append((args, kwargs))

	assert perform(_Self(), "收回") is True
	assert clicks == [((210, 278), {"hwnd": 123})]


def test_perform_recall_confirmation_action_prefers_ocr_click_point_for_modern_recall():
	module_path = Path(__file__).resolve().parents[1] / "addon" / "appModules" / "line.py"
	source = module_path.read_text(encoding="utf-8")
	module = ast.parse(source)
	app_module = next(
		node
		for node in module.body
		if isinstance(node, ast.ClassDef) and node.name == "AppModule"
	)
	method = next(
		node
		for node in app_module.body
		if isinstance(node, ast.FunctionDef) and node.name == "_performRecallConfirmationAction"
	)
	compact_helper = next(
		node
		for node in module.body
		if isinstance(node, ast.FunctionDef) and node.name == "_isCompactModernRecallDialog"
	)
	ns = {
		"log": _Log(),
		"_getRecallDialogFallbackClickPoint": lambda *args, **kwargs: None,
		"_": lambda text: text,
	}
	exec(
		compile(
			ast.Module(body=[compact_helper, method], type_ignores=[]),
			str(module_path),
			"exec",
		),
		ns,
	)
	perform = ns["_performRecallConfirmationAction"]
	clicks = []

	class _Self:
		def _refreshRecallConfirmationState(self):
			return {
				"targets": {
					"收回": {
						"element": object(),
						"rect": (100, 200, 300, 320),
						"clickPoint": (215, 284),
					},
				},
				"isModernDialog": True,
				"hwnd": 456,
				"dialogRect": (50, 50, 350, 350),
			}

		def _invokeElement(self, *args, **kwargs):
			raise AssertionError("OCR click point should win before UIA even for modern dialog")

		def _clickAtPosition(self, *args, **kwargs):
			clicks.append((args, kwargs))

	assert perform(_Self(), "收回") is True
	assert clicks == [((215, 284), {"hwnd": 456})]


def test_perform_recall_confirmation_action_prefers_compact_modern_fallback_before_uia_when_ocr_missing():
	module_path = Path(__file__).resolve().parents[1] / "addon" / "appModules" / "line.py"
	source = module_path.read_text(encoding="utf-8")
	module = ast.parse(source)
	app_module = next(
		node
		for node in module.body
		if isinstance(node, ast.ClassDef) and node.name == "AppModule"
	)
	method = next(
		node
		for node in app_module.body
		if isinstance(node, ast.FunctionDef) and node.name == "_performRecallConfirmationAction"
	)
	compact_helper = next(
		node
		for node in module.body
		if isinstance(node, ast.FunctionDef) and node.name == "_isCompactModernRecallDialog"
	)
	fallback_calls = []
	ns = {
		"log": _Log(),
		"_getRecallDialogFallbackClickPoint": lambda action, rect, **kwargs: (
			fallback_calls.append((action, rect, kwargs)) or (222, 333)
		),
		"_": lambda text: text,
	}
	exec(
		compile(
			ast.Module(body=[compact_helper, method], type_ignores=[]),
			str(module_path),
			"exec",
		),
		ns,
	)
	perform = ns["_performRecallConfirmationAction"]
	clicks = []

	class _Self:
		def _refreshRecallConfirmationState(self):
			return {
				"targets": {
					"收回": {
						"element": object(),
						"rect": (100, 200, 300, 320),
						"clickPoint": None,
					},
				},
				"actionLabels": ["收回", "取消"],
				"isModernDialog": True,
				"hwnd": 789,
				"dialogRect": (50, 50, 350, 350),
			}

		def _invokeElement(self, *args, **kwargs):
			raise AssertionError("compact modern recall should fallback-click before invoking UIA")

		def _clickAtPosition(self, *args, **kwargs):
			clicks.append((args, kwargs))

	assert perform(_Self(), "收回") is True
	assert fallback_calls == [
		("收回", (50, 50, 350, 350), {"isModernDialog": True, "availableActions": ["收回", "取消"]})
	]
	assert clicks == [((222, 333), {"hwnd": 789})]


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
