from .._virtualWindow import VirtualWindow
from .._utils import ocrGetText, message
from logHandler import log

import difflib
import re

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
	"回覆",
	"複製",
	"分享",
	"收回",
	"刪除",
	"翻譯",
	"傳送至Keep筆記",
	"儲存至記事本",
	"設為公告",
	"另存新檔",
	"轉傳",
)

_MENU_LABEL_ALIASES = {
	"回覆": ("回覆", "回復", "回覧"),
	"複製": ("複製", "复制"),
	"分享": ("分享",),
	"收回": ("收回",),
	"刪除": ("刪除", "删除"),
	"翻譯": ("翻譯", "翻译"),
	"傳送至Keep筆記": (
		"傳送至Keep筆記",
		"傳送至 Keep 筆記",
		"傳送至Keep",
		"傳送至 Keep",
	),
	"儲存至記事本": ("儲存至記事本",),
	"設為公告": ("設為公告",),
	"另存新檔": ("另存新檔",),
	"轉傳": ("轉傳",),
}

_NOISE_LINE_RE = re.compile(r"^[\W_]*[\d０-９]+[\W_]*$|^[A-Za-z]{4,}$")


def _normalizeLineText(text):
	text = _removeCJKSpaces((text or "").strip())
	text = text.replace(" ", "")
	return text


def _matchMenuLabel(text):
	normalized = _normalizeLineText(text)
	if not normalized:
		return None

	for canonical, aliases in _MENU_LABEL_ALIASES.items():
		for alias in aliases:
			aliasNorm = _normalizeLineText(alias)
			if aliasNorm in normalized or normalized in aliasNorm:
				return canonical

	bestLabel = None
	bestRatio = 0.0
	for canonical in _KNOWN_MENU_LABELS:
		canonicalNorm = _normalizeLineText(canonical)
		ratio = difflib.SequenceMatcher(None, normalized, canonicalNorm).ratio()
		if ratio > bestRatio:
			bestRatio = ratio
			bestLabel = canonical

	if bestLabel and bestRatio >= 0.62:
		return bestLabel
	return None


def _extractOcrLines(result):
	rawLines = getattr(result, "lines", None) or []
	extracted = []
	for rawLine in rawLines:
		text = getattr(rawLine, "text", "") or ""
		text = text.strip()
		if not text:
			continue
		rect = None
		for attr in ("boundingRect", "boundingRectangle", "rect", "location", "bounds"):
			r = getattr(rawLine, attr, None)
			if not r:
				continue
			left = getattr(r, "left", getattr(r, "x", None))
			top = getattr(r, "top", getattr(r, "y", None))
			right = getattr(r, "right", None)
			bottom = getattr(r, "bottom", None)
			if right is None and left is not None:
				width = getattr(r, "width", None)
				if width is not None:
					right = left + width
			if bottom is None and top is not None:
				height = getattr(r, "height", None)
				if height is not None:
					bottom = top + height
			if None not in (left, top, right, bottom):
				rect = (int(left), int(top), int(right), int(bottom))
				break
		extracted.append({"text": text, "rect": rect})
	return extracted


class MessageContextMenu(VirtualWindow):
	title = '訊息選單'

	@staticmethod
	def isMatchLineScreen(obj):
		return False

	def __init__(self, popupRect, rowRects=None, onAction=None):
		self.elements = []
		self.pos = -1
		self.popupRect = popupRect
		self.rowRects = rowRects or []
		self.onAction = onAction
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
			log.debug(f"LINE: MessageContextMenu OCR error: {result}")
			return

		lineInfos = _extractOcrLines(result)
		if not lineInfos:
			text = getattr(result, 'text', '') or ''
			text = _removeCJKSpaces(text.strip())
			lineInfos = [
				{"text": line.strip(), "rect": None}
				for line in text.split('\n')
				if line.strip()
			]

		if not lineInfos:
			log.debug("LINE: MessageContextMenu OCR returned no lines")
			return

		left, top, right, bottom = self.popupRect
		centerX = (left + right) // 2
		rowRects = sorted(
			[r for r in self.rowRects if r],
			key=lambda r: (r[1] + r[3]) / 2,
		) if self.rowRects else []

		elements = []
		for line in lineInfos:
			rawText = line["text"]
			menuLabel = _matchMenuLabel(rawText)
			normalized = _normalizeLineText(rawText)
			if not menuLabel:
				if normalized and not _NOISE_LINE_RE.fullmatch(normalized):
					log.debug(
						f"LINE: MessageContextMenu skipping non-menu OCR line: {rawText!r}"
					)
				continue
			elements.append({
				"name": menuLabel,
				"role": None,
				"clickPoint": None,
				"_lineRect": line.get("rect"),
			})

		# Fallback: if no known labels matched, use raw OCR lines
		if not elements:
			for line in lineInfos:
				rawText = line["text"]
				normalized = _normalizeLineText(rawText)
				if normalized and not _NOISE_LINE_RE.fullmatch(normalized):
					elements.append({
						"name": rawText,
						"role": None,
						"clickPoint": None,
						"_lineRect": line.get("rect"),
					})

		if not elements:
			log.debug("LINE: MessageContextMenu no valid menu items found")
			return

		# Assign click points from UIA row rects or OCR line rects
		if rowRects and len(rowRects) >= len(elements):
			for i, element in enumerate(elements):
				rLeft, rTop, rRight, rBottom = rowRects[i]
				element["clickPoint"] = (
					(rLeft + rRight) // 2,
					(rTop + rBottom) // 2,
				)
		else:
			# Use OCR line rects or evenly distribute
			itemHeight = (bottom - top) / max(len(elements), 1)
			for index, element in enumerate(elements):
				lineRect = element.get("_lineRect")
				if lineRect:
					lLeft, lTop, lRight, lBottom = lineRect
					element["clickPoint"] = (
						(lLeft + lRight) // 2,
						(lTop + lBottom) // 2,
					)
				else:
					itemCenterY = int(top + itemHeight * index + itemHeight / 2)
					element["clickPoint"] = (centerX, itemCenterY)

		# Clean up temporary data
		for element in elements:
			element.pop("_lineRect", None)

		self.elements = elements
		log.info(
			f"LINE: MessageContextMenu found {len(self.elements)} items: "
			f"{[e['name'] for e in self.elements]}"
		)

		if self.elements:
			self.pos = 0
			self.show()

	def click(self):
		element = self.element
		actionName = element.get("name") if element else None
		hasClickPoint = bool(element and element.get("clickPoint"))
		super().click()
		VirtualWindow.currentWindow = None
		if hasClickPoint and callable(self.onAction):
			try:
				self.onAction(actionName)
			except Exception:
				log.debug("LINE: MessageContextMenu action callback failed", exc_info=True)

	def dismiss(self):
		VirtualWindow.currentWindow = None
		from keyboardHandler import KeyboardInputGesture
		KeyboardInputGesture.fromName("escape").send()
