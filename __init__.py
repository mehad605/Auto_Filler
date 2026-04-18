from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.addcards import AddCards
from aqt.utils import tooltip
from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QApplication,
    Qt,
    QTimer,
    QTextBrowser,
    QPushButton,
)
import re
import json

# ─────────────────────────────────────────────
#  GLOBAL STATE
# ─────────────────────────────────────────────
CLIPBOARD_MODE = None   # "ENTER" | "CREATE" | None
CURRENT_EDITOR = None
CARD_QUEUE = []         # cards yet to be shown (dicts)
LAST_CLIPBOARD_TEXT = "" # avoid resetting queue on focus/inactive same-text
POLL_TIMER = None        # polling for background clipboard support

# ─────────────────────────────────────────────
#  PARSING
# ─────────────────────────────────────────────

def _parse_text_cards(text: str) -> list:
    """
    Parse the custom text format into card dicts.

        ===!!Note Type!!===
        ==**Field Name**==
        content …
        ==**Another Field**==
        content …
    """
    # Backtick magic: `` → ```
    text = re.sub(r"(?<!`)``(?!`)", "```", text)

    cards = []
    card_blocks = re.split(r"===!!(.*?)!!===", text)

    i = 1
    while i + 1 <= len(card_blocks) - 1:
        card_type    = card_blocks[i].strip()
        card_content = card_blocks[i + 1]
        i += 2

        if not card_type:
            continue

        field_parts = re.split(r"==\*\*(.*?)\*\*==", card_content)

        fields: dict = {}
        tags:   list = []
        j = 1
        while j + 1 <= len(field_parts) - 1:
            fname    = field_parts[j].strip()
            fcontent = field_parts[j + 1].strip()
            j += 2

            if not fname:
                continue
            if fname.lower() == "tags":
                tags = [t for t in fcontent.split() if t]
            else:
                fields[fname] = fcontent.replace("\n", "<br>")

        if fields:
            cards.append({"type": card_type, "fields": fields, "tags": tags})

    return cards


def _parse_json_cards(text: str) -> list:
    """
    Parse a JSON array (or single object) of card dicts.

    Expected shape:
        [
          {
            "type": "Basic",
            "Front": "Question text",
            "Back": "Answer text",
            "tags": ["tag1", "tag2"]   ← array OR space-separated string
          },
          ...
        ]

    Rules:
      • "type"  (required) — note type name; case-insensitive match
      • "tags"  (optional) — list or space-separated string
      • every other key   — treated as a field name (case-sensitive)
      • unknown / missing fields are silently skipped
    """
    try:
        data = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return []

    # Accept both a bare object and an array
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    cards = []
    for item in data:
        if not isinstance(item, dict):
            continue

        # Locate the note-type key (support a few common aliases)
        card_type = (
            item.get("type")
            or item.get("Type")
            or item.get("note_type")
            or item.get("noteType")
            or item.get("card_type")
        )
        if not card_type:
            continue
        card_type = str(card_type).strip()

        fields: dict = {}
        tags:   list = []

        for key, val in item.items():
            if key.lower() in ("type", "note_type", "notetype", "card_type"):
                continue
            if key.lower() == "tags":
                if isinstance(val, list):
                    tags = [str(t).strip() for t in val if str(t).strip()]
                else:
                    tags = [t for t in str(val).split() if t]
            else:
                # Normalise value: convert newlines for Anki
                fields[key] = str(val).replace("\n", "<br>")

        if fields:
            cards.append({"type": card_type, "fields": fields, "tags": tags})

    return cards


def parse_cards(text: str) -> list:
    """
    Auto-detect format (JSON vs custom text) and return card dicts.
    JSON is tried first; falls back to the text format on failure.
    """
    stripped = text.strip()
    if stripped.startswith(("[", "{")):
        cards = _parse_json_cards(stripped)
        if cards:
            return cards
    return _parse_text_cards(text)


# ─────────────────────────────────────────────
#  FILL EDITOR
# ─────────────────────────────────────────────

def fill_editor_with_card(editor: Editor, card: dict, callback=None):
    """
    1. Switch the note type (if recognisable).
    2. Clear all fields, set tags, fill matching fields.
    3. Call optional callback when done.
    """

    def _cb():
        if callback:
            callback()

    try:
        if not editor.note:
            _cb(); return False
    except Exception:
        _cb(); return False

    # ── Switch note type ──────────────────────
    switched = False
    card_type = card.get("type", "")
    if card_type:
        note_types = {name.lower(): name for name in mw.col.models.all_names()}
        canonical = note_types.get(card_type.lower())
        if canonical:
            model = mw.col.models.by_name(canonical)
            if model:
                parent = editor.widget
                while parent and not isinstance(parent, AddCards):
                    parent = parent.parent()
                if parent and hasattr(parent, "set_note_type"):
                    parent.set_note_type(model["id"])
                    switched = True

    # ── Fill fields (after giving the UI time to update) ──
    def do_fill():
        try:
            if not editor.note:
                _cb(); return
        except Exception:
            _cb(); return

        field_map = {name: idx for idx, name in enumerate(editor.note.keys())}

        # Clear everything first
        for idx in range(len(editor.note.fields)):
            editor.note.fields[idx] = ""
        editor.note.tags = card.get("tags", [])

        changed = False
        for fname, fval in card["fields"].items():
            if fname in field_map:
                editor.note.fields[field_map[fname]] = fval
                changed = True

        if changed:
            editor.loadNoteKeepingFocus()

        _cb()

    # Slightly longer delay when note type just changed
    QTimer.singleShot(400 if switched else 60, do_fill)
    return True


# ─────────────────────────────────────────────
#  PROCESS CLIPBOARD TEXT
# ─────────────────────────────────────────────

def process_text(editor: Editor, text: str, auto_add: bool):
    global CARD_QUEUE

    if not text:
        return

    cards = parse_cards(text)
    if not cards:
        return

    if auto_add:
        # ⚡ Lightning / Auto-Create: create every card without user clicks
        total = len(cards)

        def process_lightning(index):
            if index >= total:
                tooltip(f"⚡ Done! Created {total} card(s).")
                return

            def after_fill():
                editor.parentWindow.add_current_note()
                QTimer.singleShot(300, lambda: process_lightning(index + 1))

            fill_editor_with_card(editor, cards[index], callback=after_fill)

        process_lightning(0)

    else:
        # 📋 Auto-Fill: show first card; rest go into queue
        CARD_QUEUE = list(cards[1:])
        fill_editor_with_card(editor, cards[0])
        if CARD_QUEUE:
            tooltip(f"📋 Loaded card 1 of {len(cards)}. {len(CARD_QUEUE)} remaining in queue.")
        else:
            tooltip("📋 Card loaded.")


# ─────────────────────────────────────────────
#  QUEUE CALLBACKS
# ─────────────────────────────────────────────

def on_card_added(note):
    """Fired after user clicks Add — feed the next queued card."""
    global CARD_QUEUE, CURRENT_EDITOR, CLIPBOARD_MODE
    if CLIPBOARD_MODE == "ENTER" and CURRENT_EDITOR and CARD_QUEUE:
        next_card = CARD_QUEUE.pop(0)
        QTimer.singleShot(200, lambda: fill_editor_with_card(CURRENT_EDITOR, next_card))
        if CARD_QUEUE:
            tooltip(f"Next card loaded. {len(CARD_QUEUE)} remaining.")
        else:
            tooltip("✅ Last card loaded — queue will be complete after this.")


def discard_current_card():
    """Skip the current card (don't add it) and load the next one."""
    global CARD_QUEUE, CURRENT_EDITOR, CLIPBOARD_MODE
    if CLIPBOARD_MODE != "ENTER" or not CURRENT_EDITOR:
        tooltip("Auto-Fill mode is not active.")
        return

    if not CARD_QUEUE:
        # 🗑️ Issue 1: nothing left to skip, so clear the fields instead
        try:
            for idx in range(len(CURRENT_EDITOR.note.fields)):
                CURRENT_EDITOR.note.fields[idx] = ""
            CURRENT_EDITOR.loadNoteKeepingFocus()
            tooltip("Queue empty — fields cleared.")
        except Exception:
            tooltip("Error clearing fields.")
        return

    next_card = CARD_QUEUE.pop(0)
    fill_editor_with_card(CURRENT_EDITOR, next_card)
    remaining = len(CARD_QUEUE)
    QTimer.singleShot(500, lambda: tooltip(
        f"Card skipped. {remaining} remaining." if remaining
        else "Card skipped. Queue complete."
    ))


# ─────────────────────────────────────────────
#  CLIPBOARD MONITOR
# ─────────────────────────────────────────────

def on_clipboard_change():
    global CLIPBOARD_MODE, CURRENT_EDITOR, LAST_CLIPBOARD_TEXT
    if not CLIPBOARD_MODE or not CURRENT_EDITOR:
        return

    # Basic safety check for editor
    try:
        if not CURRENT_EDITOR.widget:
            return
    except (AttributeError, RuntimeError):
        # Editor likely closed/deleted
        return

    try:
        text = QApplication.clipboard().text().strip()
        if not text or text == LAST_CLIPBOARD_TEXT:
            return

        LAST_CLIPBOARD_TEXT = text
        process_text(CURRENT_EDITOR, text, auto_add=(CLIPBOARD_MODE == "CREATE"))
    except Exception:
        pass


# ─────────────────────────────────────────────
#  MODE TOGGLE
# ─────────────────────────────────────────────

def toggle_mode(editor: Editor, mode: str):
    global CLIPBOARD_MODE, CURRENT_EDITOR, CARD_QUEUE, LAST_CLIPBOARD_TEXT, POLL_TIMER
    if CLIPBOARD_MODE == mode:
        # Off
        CLIPBOARD_MODE = None
        CARD_QUEUE = []
        LAST_CLIPBOARD_TEXT = ""
        if POLL_TIMER:
            POLL_TIMER.stop()
            POLL_TIMER = None
        tooltip("Monitor off.")
    else:
        # On
        CLIPBOARD_MODE = mode
        CURRENT_EDITOR = editor
        LAST_CLIPBOARD_TEXT = QApplication.clipboard().text().strip()
        name = "Auto-Fill" if mode == "ENTER" else "Auto-Create"
        tooltip(f"{name} mode ON — waiting for clipboard…")

        # Start polling for background support (helps on Wayland/background apps)
        if not POLL_TIMER:
            POLL_TIMER = QTimer()
            POLL_TIMER.timeout.connect(on_clipboard_change)
            POLL_TIMER.start(800) # every 800ms

    highlight_button(editor, "enter",  CLIPBOARD_MODE == "ENTER")
    highlight_button(editor, "create", CLIPBOARD_MODE == "CREATE")


def highlight_button(editor: Editor, btn_type: str, is_active: bool):
    title = (
        "Toggle Monitor: Auto-Fill Only"
        if btn_type == "enter"
        else "Toggle Monitor: Auto-Fill & Create"
    )
    bg     = "#b9f6ca"        if is_active else ""
    border = "2px solid #00c853" if is_active else ""
    js = (
        f"(function(){{"
        f"  var btns=document.querySelectorAll('button');"
        f"  for(var i=0;i<btns.length;i++){{"
        f"    if(btns[i].title==='{title}'){{"
        f"      btns[i].style.backgroundColor='{bg}';"
        f"      btns[i].style.border='{border}';"
        f"      btns[i].style.borderRadius='4px';"
        f"    }}"
        f"  }}"
        f"}})();"
    )
    editor.web.eval(js)


# ─────────────────────────────────────────────
#  HELP DIALOG
# ─────────────────────────────────────────────

def help_dialog_handler(editor: Editor):
    dialog = QDialog(editor.widget)
    dialog.setWindowTitle("Auto Filler — Guide")
    dialog.resize(660, 820)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    browser = QTextBrowser()
    browser.setOpenExternalLinks(True)
    browser.setStyleSheet(
        "background:#1e1e2e; color:#cdd6f4; border:none; border-radius:8px;"
    )

    browser.setHtml("""<!DOCTYPE html>
<html>
<body style="font-family:'Segoe UI',Arial,sans-serif;padding:22px;
             color:#cdd6f4;line-height:1.75;background:#1e1e2e;margin:0;">

  <h2 style="color:#cba6f7;margin:0 0 4px;font-size:22px;letter-spacing:.4px;">
    🚀 Auto Filler — Complete Guide
  </h2>
  <hr style="border:none;border-top:1px solid #45475a;margin:0 0 20px;"/>

  <p style="margin:0 0 18px;color:#a6adc8;">
    Auto Filler accepts <b>two input formats</b> — it detects which one you copied
    automatically. Both support all the same features.
  </p>


  <!-- ══════════════════════════════════════════
       FORMAT 1 — CUSTOM TEXT
  ══════════════════════════════════════════ -->
  <h3 style="color:#89b4fa;margin:0 0 8px;">
    📄 Format 1 — Custom Text
    <span style="font-size:11px;color:#a6adc8;font-weight:normal;margin-left:8px;">
      great for hand-writing cards
    </span>
  </h3>

  <div style="background:#181825;padding:14px 18px;border-radius:8px;
              font-family:'Courier New',monospace;font-size:12.5px;
              line-height:2;border-left:3px solid #cba6f7;">
    <span style="color:#f38ba8;font-weight:bold;">===!!Basic!!===</span><br>
    <span style="color:#a6e3a1;">==**Front**==</span><br>
    What is the capital of France?<br>
    <span style="color:#a6e3a1;">==**Back**==</span><br>
    Paris<br>
    <span style="color:#a6e3a1;">==**Tags**==</span><br>
    geography europe<br><br>
    <span style="color:#f38ba8;font-weight:bold;">===!!Cloze!!===</span><br>
    <span style="color:#a6e3a1;">==**Text**==</span><br>
    {{c1::Paris}} is the capital of France.
  </div>

  <h4 style="color:#a6adc8;margin:14px 0 8px;font-size:13px;">Syntax</h4>
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <tr style="background:#313244;">
      <td style="padding:9px 14px;border-radius:6px 0 0 6px;width:44%;white-space:nowrap;">
        <code style="color:#f38ba8;">===!!Note Type!!===</code>
      </td>
      <td style="padding:9px 14px;border-radius:0 6px 6px 0;">
        Starts a new card and sets its note type
      </td>
    </tr>
    <tr><td colspan="2" style="height:5px;"></td></tr>
    <tr style="background:#313244;">
      <td style="padding:9px 14px;border-radius:6px 0 0 6px;white-space:nowrap;">
        <code style="color:#a6e3a1;">==**Field Name**==</code>
      </td>
      <td style="padding:9px 14px;border-radius:0 6px 6px 0;">
        Content on the lines below goes into this field
      </td>
    </tr>
    <tr><td colspan="2" style="height:5px;"></td></tr>
    <tr style="background:#313244;">
      <td style="padding:9px 14px;border-radius:6px 0 0 6px;white-space:nowrap;">
        <code style="color:#fab387;">==**Tags**==</code>
      </td>
      <td style="padding:9px 14px;border-radius:0 6px 6px 0;">
        Special field — space-separated tags
        (e.g.&nbsp;<code>math algebra ch1</code>)
      </td>
    </tr>
  </table>

  <p style="margin:10px 0 0;font-size:12.5px;color:#a6adc8;">
    💡 Double backtick&nbsp;<code>``</code> is auto-converted to triple&nbsp;<code>```</code>
    (useful for code blocks). Line breaks inside a field become
    <code>&lt;br&gt;</code> tags in Anki.
  </p>


  <!-- ══════════════════════════════════════════
       FORMAT 2 — JSON
  ══════════════════════════════════════════ -->
  <h3 style="color:#89b4fa;margin:26px 0 8px;">
    🤖 Format 2 — JSON
    <span style="font-size:11px;color:#a6adc8;font-weight:normal;margin-left:8px;">
      ideal for AI-generated cards
    </span>
  </h3>

  <p style="margin:0 0 10px;">
    Copy a JSON array — the addon detects it automatically. This is the
    recommended format when asking an AI to generate flashcards for you,
    because AI models produce valid JSON very reliably.
  </p>

  <div style="background:#181825;padding:14px 18px;border-radius:8px;
              font-family:'Courier New',monospace;font-size:12.5px;
              line-height:1.9;border-left:3px solid #89b4fa;">
    [<br>
    &nbsp;&nbsp;{<br>
    &nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#f38ba8;">"type"</span>:
      <span style="color:#a6e3a1;">"Basic"</span>,<br>
    &nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#cdd6f4;">"Front"</span>:
      <span style="color:#a6e3a1;">"What is the capital of France?"</span>,<br>
    &nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#cdd6f4;">"Back"</span>:
      <span style="color:#a6e3a1;">"Paris"</span>,<br>
    &nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#fab387;">"tags"</span>:
      <span style="color:#a6e3a1;">["geography", "europe"]</span><br>
    &nbsp;&nbsp;},<br>
    &nbsp;&nbsp;{<br>
    &nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#f38ba8;">"type"</span>:
      <span style="color:#a6e3a1;">"Cloze"</span>,<br>
    &nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#cdd6f4;">"Text"</span>:
      <span style="color:#a6e3a1;">"{{c1::Paris}} is the capital of France."</span><br>
    &nbsp;&nbsp;}<br>
    ]
  </div>

  <h4 style="color:#a6adc8;margin:14px 0 8px;font-size:13px;">JSON Key Rules</h4>
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <tr style="background:#313244;">
      <td style="padding:9px 14px;border-radius:6px 0 0 6px;width:20%;white-space:nowrap;">
        <code style="color:#f38ba8;">"type"</code>
      </td>
      <td style="padding:9px 14px;border-radius:0 6px 6px 0;">
        <b>Required.</b> The note type name. Case-insensitive match against your Anki collection.
        Also accepted: <code>"note_type"</code>, <code>"noteType"</code>, <code>"card_type"</code>
      </td>
    </tr>
    <tr><td colspan="2" style="height:5px;"></td></tr>
    <tr style="background:#313244;">
      <td style="padding:9px 14px;border-radius:6px 0 0 6px;white-space:nowrap;">
        <code style="color:#fab387;">"tags"</code>
      </td>
      <td style="padding:9px 14px;border-radius:0 6px 6px 0;">
        <b>Optional.</b> Either a JSON array
        (<code>["tag1","tag2"]</code>) or a
        space-separated string (<code>"tag1 tag2"</code>)
      </td>
    </tr>
    <tr><td colspan="2" style="height:5px;"></td></tr>
    <tr style="background:#313244;">
      <td style="padding:9px 14px;border-radius:6px 0 0 6px;white-space:nowrap;">
        <i style="color:#a6adc8;">any other key</i>
      </td>
      <td style="padding:9px 14px;border-radius:0 6px 6px 0;">
        Treated as a field name — <b>case-sensitive</b>, must match your note type exactly.
        Unknown keys are silently skipped.
      </td>
    </tr>
  </table>

  <div style="background:#2a2a3d;border:1px solid #45475a;border-radius:8px;
              padding:12px 16px;margin-top:14px;font-size:12.5px;">
    <b style="color:#cba6f7;">💬 Suggested AI prompt:</b><br>
    <span style="color:#a6adc8;">
      "Generate Anki flashcards from the text below. Return a JSON array where each
      object has a <code style='background:#313244;padding:1px 4px;'>type</code> key
      (note type name), a
      <code style='background:#313244;padding:1px 4px;'>tags</code> key (array of strings),
      and one key per field matching the note type's field names exactly.
      Return only the JSON array with no other text."
    </span>
  </div>


  <!-- ══════════════════════════════════════════
       BUTTONS
  ══════════════════════════════════════════ -->
  <h3 style="color:#89b4fa;margin:26px 0 8px;">🎮 Button Reference</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px;">

    <tr style="background:#313244;">
      <td style="padding:10px 14px;border-radius:6px 0 0 6px;
                 text-align:center;font-size:20px;width:50px;">📋</td>
      <td style="padding:10px 14px;border-radius:0 6px 6px 0;">
        <b>Auto-Fill Mode</b><br>
        Copy your text/JSON → first card fills in automatically.
        Click <b>Add</b> in Anki to advance to the next card.
        Click 📋 again to deactivate.
      </td>
    </tr>

    <tr><td colspan="2" style="height:5px;"></td></tr>

    <tr style="background:#313244;">
      <td style="padding:10px 14px;border-radius:6px 0 0 6px;
                 text-align:center;font-size:20px;">⚡</td>
      <td style="padding:10px 14px;border-radius:0 6px 6px 0;">
        <b>Auto-Create Mode</b><br>
        Copy your text/JSON → <em>every card</em> is created instantly, hands-free.
        Perfect for bulk AI-generated imports. Click ⚡ again to deactivate.
      </td>
    </tr>

    <tr><td colspan="2" style="height:5px;"></td></tr>

    <tr style="background:#313244;">
      <td style="padding:10px 14px;border-radius:6px 0 0 6px;
                 text-align:center;font-size:20px;">🗑️</td>
      <td style="padding:10px 14px;border-radius:0 6px 6px 0;">
        <b>Discard &amp; Skip</b><br>
        Throw away the current card without adding it, then load the next one.
        Only works in Auto-Fill mode.
      </td>
    </tr>

    <tr><td colspan="2" style="height:5px;"></td></tr>

    <tr style="background:#313244;">
      <td style="padding:10px 14px;border-radius:6px 0 0 6px;
                 text-align:center;font-size:20px;">❓</td>
      <td style="padding:10px 14px;border-radius:0 6px 6px 0;">
        <b>Help</b> — Opens this guide.
      </td>
    </tr>

  </table>


  <!-- ══════════════════════════════════════════
       TIPS
  ══════════════════════════════════════════ -->
  <h3 style="color:#89b4fa;margin:26px 0 8px;">💡 General Tips</h3>
  <ul style="padding-left:22px;margin:0;line-height:2.1;">
    <li>Field names are <b>case-sensitive</b> in both formats — match your note type exactly.</li>
    <li>Unrecognised note types or field names are <b>silently skipped</b> — no crashes.</li>
    <li>The active mode button glows <span style="color:#a6e3a1;font-weight:bold;">green</span>.
        Only one mode can be active at a time.</li>
    <li>Format is <b>auto-detected</b> — no need to switch anything when alternating between
        text and JSON.</li>
    <li>A single JSON object <code>{…}</code> (without the outer array) also works.</li>
  </ul>

</body>
</html>""")

    layout.addWidget(browser)

    btn = QPushButton("✕  Close")
    btn.setStyleSheet(
        "padding:9px 26px;font-weight:bold;font-size:13px;"
        "background:#cba6f7;color:#1e1e2e;border:none;border-radius:6px;"
    )
    btn.clicked.connect(dialog.accept)
    layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

    dialog.exec()


# ─────────────────────────────────────────────
#  TOOLBAR BUTTONS
# ─────────────────────────────────────────────

def add_buttons(buttons, editor: Editor):
    buttons.append(editor.addButton(
        None, "af_fill",
        lambda *_: toggle_mode(editor, "ENTER"),
        tip="Toggle Monitor: Auto-Fill Only",
        label="📋",
    ))
    buttons.append(editor.addButton(
        None, "af_create",
        lambda *_: toggle_mode(editor, "CREATE"),
        tip="Toggle Monitor: Auto-Fill & Create",
        label="⚡",
    ))
    buttons.append(editor.addButton(
        None, "af_discard",
        lambda *_: discard_current_card(),
        tip="Discard current card and move to next",
        label="🗑️",
    ))
    buttons.append(editor.addButton(
        None, "af_help",
        lambda *_: help_dialog_handler(editor),
        tip="Help / Guide",
        label="❓",
    ))


# ─────────────────────────────────────────────
#  REGISTER HOOKS
# ─────────────────────────────────────────────
gui_hooks.editor_did_init_buttons.append(add_buttons)
gui_hooks.add_cards_did_add_note.append(on_card_added)
QApplication.clipboard().dataChanged.connect(on_clipboard_change)
