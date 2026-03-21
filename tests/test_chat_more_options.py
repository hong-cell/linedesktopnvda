from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_chat_more_options_module():
	module_name = "addon.appModules._virtualWindows.chatMoreOptions"
	module_path = (
		Path(__file__).resolve().parents[1]
		/ "addon"
		/ "appModules"
		/ "_virtualWindows"
		/ "chatMoreOptions.py"
	)

	for name in (
		"addon",
		"addon.appModules",
		"addon.appModules._virtualWindows",
	):
		pkg = types.ModuleType(name)
		pkg.__path__ = []  # type: ignore[attr-defined]
		sys.modules[name] = pkg

	virtual_window_mod = types.ModuleType("addon.appModules._virtualWindow")

	class VirtualWindow:
		currentWindow = None

	virtual_window_mod.VirtualWindow = VirtualWindow
	sys.modules["addon.appModules._virtualWindow"] = virtual_window_mod

	utils_mod = types.ModuleType("addon.appModules._utils")
	utils_mod.ocrGetText = lambda *args, **kwargs: None
	utils_mod.message = lambda *args, **kwargs: None
	sys.modules["addon.appModules._utils"] = utils_mod

	log_handler_mod = types.ModuleType("logHandler")

	class _Log:
		def debug(self, *args, **kwargs):
			pass

		def info(self, *args, **kwargs):
			pass

	log_handler_mod.log = _Log()
	sys.modules["logHandler"] = log_handler_mod

	spec = importlib.util.spec_from_file_location(module_name, module_path)
	assert spec and spec.loader
	module = importlib.util.module_from_spec(spec)
	sys.modules[module_name] = module
	spec.loader.exec_module(module)
	return module


chat_more_options = _load_chat_more_options_module()


def test_match_menu_label_handles_known_ocr_variants():
	assert chat_more_options._matchMenuLabel("眧片 • 影片") == "照片・影片"
	assert chat_more_options._matchMenuLabel("冃景言殳定") == "背景設定"
	assert chat_more_options._matchMenuLabel("5") is None
	assert chat_more_options._matchMenuLabel("llnedes") is None


def test_build_menu_elements_keeps_only_actionable_items_and_uses_line_rects():
	lines = [
		{"text": "5", "rect": (1070, 95, 1090, 118)},
		{"text": "llnedes", "rect": (1080, 122, 1160, 144)},
		{"text": "開啟提醒", "rect": (1084, 150, 1178, 182)},
		{"text": "邀請", "rect": (1084, 205, 1138, 236)},
		{"text": "眧片 • 影片", "rect": (1084, 315, 1188, 348)},
		{"text": "冃景言殳定", "rect": (1084, 545, 1188, 578)},
		{"text": "封鎖", "rect": (1084, 645, 1138, 676)},
		{"text": "Se ng 功能的加密保護", "rect": (1084, 688, 1260, 713)},
	]

	elements = chat_more_options._buildMenuElements(
		lines,
		(1055, 89, 1355, 718),
	)

	assert [element["name"] for element in elements] == [
		"開啟提醒",
		"邀請",
		"照片・影片",
		"背景設定",
		"封鎖",
	]
	assert elements[0]["clickPoint"] == (1131, 166)
	assert elements[-1]["clickPoint"] == (1111, 660)


def test_build_menu_elements_assigns_fallback_clickpoints_when_rects_are_missing():
	lines = [
		{"text": "5", "rect": None},
		{"text": "llnedes", "rect": None},
		{"text": "開啟提醒", "rect": None},
		{"text": "邀請", "rect": None},
		{"text": "冃景言殳定", "rect": None},
	]

	elements = chat_more_options._buildMenuElements(
		lines,
		(1000, 100, 1300, 400),
	)

	assert [element["name"] for element in elements] == [
		"開啟提醒",
		"邀請",
		"背景設定",
	]
	assert [element["clickPoint"] for element in elements] == [
		(1150, 150),
		(1150, 250),
		(1150, 350),
	]
