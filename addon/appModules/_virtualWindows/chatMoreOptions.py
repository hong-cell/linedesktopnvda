from .._virtualWindow import VirtualWindow
from .._utils import ocrGetText, message
from logHandler import log

import difflib
import re
from typing import Any

_CJK_CHAR = (
	r'[\u2E80-\u9FFF\uF900-\uFAFF'
	r'\U00020000-\U0002A6DF\U0002A700-\U0002EBEF\U00030000-\U000323AF]'
)
_CJK_SPACE_RE = re.compile(
	r'(?<=' + _CJK_CHAR + r') (?=' + _CJK_CHAR + r')'
)

def _removeCJKSpaces(text):
	return _CJK_SPACE_RE.sub('', text)


_KNOWN_MENU_LABELS = (
	"開啟提醒",
	"關閉提醒",
	"邀請",
	"相簿",
	"照片・影片",
	"檔案",
	"連結",
	"投票",
	"儲存聊天",
	"背景設定",
	"檢舉",
	"封鎖",
)

_MENU_LABEL_ALIASES = {
	"開啟提醒": ("開啟提醒",),
	"關閉提醒": ("關閉提醒",),
	"邀請": ("邀請",),
	"相簿": ("相簿",),
	"照片・影片": ("照片影片", "照片影⽚", "照片影像", "照片•影片", "照片‧影片", "眧片影片", "照片 影片"),
	"檔案": ("檔案",),
	"連結": ("連結",),
	"投票": ("投票",),
	"儲存聊天": ("儲存聊天",),
	"背景設定": ("背景設定", "冃景言殳定", "背景设定"),
	"檢舉": ("檢舉",),
	"封鎖": ("封鎖",),
}

_NOISE_LINE_RE = re.compile(r"^[\W_]*[\d０-９]+[\W_]*$|^[A-Za-z]{4,}$")


def _normalizeLineText(text: str) -> str:
	text = _removeCJKSpaces((text or "").strip())
	text = text.replace("•", "・").replace("‧", "・").replace("·", "・")
	text = text.replace("・", "")
	text = text.replace(" ", "")
	return text


def _matchMenuLabel(text: str) -> str | None:
	normalized = _normalizeLineText(text)
	if not normalized:
		return None

	for canonical, aliases in _MENU_LABEL_ALIASES.items():
		for alias in aliases:
			if alias in normalized:
				return canonical

	bestLabel = None
	bestRatio = 0.0
	for canonical in _KNOWN_MENU_LABELS:
		ratio = difflib.SequenceMatcher(None, normalized, canonical).ratio()
		if ratio > bestRatio:
			bestRatio = ratio
			bestLabel = canonical

	if bestLabel and bestRatio >= 0.62:
		return bestLabel
	return None


def _extractRectLike(obj: Any) -> tuple[int, int, int, int] | None:
	for attr in ("boundingRect", "boundingRectangle", "rect", "location", "bounds"):
		rect = getattr(obj, attr, None)
		if not rect:
			continue
		left = getattr(rect, "left", getattr(rect, "x", None))
		top = getattr(rect, "top", getattr(rect, "y", None))
		right = getattr(rect, "right", None)
		bottom = getattr(rect, "bottom", None)
		if right is None and left is not None:
			width = getattr(rect, "width", None)
			if width is not None:
				right = left + width
		if bottom is None and top is not None:
			height = getattr(rect, "height", None)
			if height is not None:
				bottom = top + height
		if None not in (left, top, right, bottom):
			return (int(left), int(top), int(right), int(bottom))

	for attrs in (
		("left", "top", "right", "bottom"),
		("x", "y", "width", "height"),
	):
		values = [getattr(obj, attr, None) for attr in attrs]
		if any(value is None for value in values):
			continue
		left, top, third, fourth = values
		if attrs[2] == "right":
			return (int(left), int(top), int(third), int(fourth))
		return (int(left), int(top), int(left + third), int(top + fourth))

	return None


def _extractOcrLines(result: Any) -> list[dict[str, Any]]:
	rawLines = getattr(result, "lines", None) or []
	extracted: list[dict[str, Any]] = []
	for rawLine in rawLines:
		text = getattr(rawLine, "text", "") or ""
		text = text.strip()
		if not text:
			continue
		extracted.append({
			"text": text,
			"rect": _extractRectLike(rawLine),
		})
	return extracted


def _buildMenuElements(
	lines: list[dict[str, Any]],
	popupRect: tuple[int, int, int, int],
) -> list[dict[str, Any]]:
	left, top, right, bottom = popupRect
	centerX = (left + right) // 2
	elements: list[dict[str, Any]] = []

	for line in lines:
		rawText = line["text"]
		menuLabel = _matchMenuLabel(rawText)
		if not menuLabel:
			normalized = _normalizeLineText(rawText)
			if normalized and not _NOISE_LINE_RE.fullmatch(normalized):
				log.debug(
					f"LINE: ChatMoreOptions skipping non-menu OCR line: {rawText!r}"
				)
			continue

		rect = line.get("rect")
		if rect:
			lineLeft, lineTop, lineRight, lineBottom = rect
			if (
				lineRight <= left
				or lineLeft >= right
				or lineBottom <= top
				or lineTop >= bottom
			):
				rect = None
			else:
				clickY = int((lineTop + lineBottom) / 2)
				clickX = int((lineLeft + lineRight) / 2)
		if not rect:
			clickY = None
			clickX = centerX

		elements.append({
			"name": menuLabel,
			"role": None,
			"clickPoint": (clickX, clickY) if clickY is not None else None,
		})

	if elements:
		itemHeight = (bottom - top) / len(elements)
		for index, element in enumerate(elements):
			if element["clickPoint"] is None:
				itemCenterY = int(top + itemHeight * index + itemHeight / 2)
				element["clickPoint"] = (centerX, itemCenterY)
		return elements

	textLines = [line["text"].strip() for line in lines if line["text"].strip()]
	if not textLines:
		return []

	itemHeight = (bottom - top) / len(textLines)
	for i, text in enumerate(textLines):
		normalized = _normalizeLineText(text)
		if _NOISE_LINE_RE.fullmatch(normalized):
			continue
		itemCenterY = int(top + itemHeight * i + itemHeight / 2)
		elements.append({
			"name": text,
			"role": None,
			"clickPoint": (centerX, itemCenterY),
		})
	return elements


class ChatMoreOptions(VirtualWindow):
	title = '更多選項'

	@staticmethod
	def isMatchLineScreen(obj):
		return False

	def __init__(self, popupRect):
		self.elements = []
		self.pos = -1
		self.popupRect = popupRect
		left, top, right, bottom = popupRect
		width = right - left
		height = bottom - top
		if width > 0 and height > 0:
			ocrGetText(left, top, width, height, self._onOcrResult)
		message(self.title)

	def makeElements(self):
		pass

	def _onOcrResult(self, result):
		if not result or isinstance(result, Exception):
			log.debug(f"LINE: ChatMoreOptions OCR error: {result}")
			return

		lineInfos = _extractOcrLines(result)
		if not lineInfos:
			text = getattr(result, 'text', '') or ''
			text = _removeCJKSpaces(text.strip())
			lineInfos = [{"text": l.strip(), "rect": None} for l in text.split('\n') if l.strip()]

		if not lineInfos:
			log.debug("LINE: ChatMoreOptions OCR returned no lines")
			return

		self.elements = _buildMenuElements(lineInfos, self.popupRect)

		log.info(f"LINE: ChatMoreOptions found {len(self.elements)} items: {[e['name'] for e in self.elements]}")

		if self.elements:
			self.pos = 0
			self.show()

	def click(self):
		super().click()
		VirtualWindow.currentWindow = None
