# Auto Filler — Bulk Anki Card Creator

**Auto Filler** is an Anki add-on that automatically fills the card editor from your clipboard. Copy card data (hand-written or AI-generated) and it lands directly in the correct fields — no clicking, no dragging, no switching note types.

---

## Features

- **Auto-Fill Mode** — Copy card data, review it in the editor, then click **Add**. The next card in your clipboard queue loads automatically.
- **Auto-Create Mode** — Copy card data and every card is created instantly, hands-free. Ideal for bulk imports.
- **Discard & Skip** — Skip a card you don't want; the next one loads.
- **Auto-detect format** — Both custom text and JSON are recognised without switching modes.
- **Auto-switch note types** — The add-on matches note types by name and maps fields correctly.
- **Clipboard monitor** — Works in the background; just copy and go.

---

## Installation

1. Open **Anki** → `Tools` → `Add-ons`.
2. Place the `Auto_Filler` folder into your Anki add-ons directory.
   - Windows: `%APPDATA%\Anki2\addons21`
   - Linux / macOS: `~/.local/share/Anki2/addons21`
3. **Restart Anki.**

---

## Usage

### Modes

Four icons appear in the *Add Cards* toolbar:

| Icon | Mode | What it does |
|------|------|-------------|
| 📋 | **Auto-Fill** | Copy card data → editor fills. Click **Add** to advance to the next card in queue. |
| ⚡ | **Auto-Create** | Copy card data → all cards created instantly, no further clicks. |
| 🗑️ | **Discard** | Skip the current card (doesn't add it) and load the next queued card. Auto-Fill only. |
| ❓ | **Help** | Opens the built-in interactive guide. |

Click the active icon again to turn the monitor off.

### Input Formats

Both formats are auto-detected — no manual switching required.

#### Format A — Custom Text

Best for hand-writing cards in a text editor.

```text
===!!Basic!!===
==**Front**==
What is the capital of France?
==**Back**==
Paris
==**Tags**==
geography europe

===!!Cloze!!===
==**Text**==
{{c1::Paris}} is the capital of France.
```

#### Format B — JSON

Best for AI-generated card batches.

```json
[
  {
    "type": "Basic",
    "Front": "What is the capital of Japan?",
    "Back": "Tokyo",
    "tags": ["asia", "geography"]
  }
]
```

| Key | Description |
|-----|-------------|
| `type` | Note type name (case-insensitive). Also accepted: `note_type`, `noteType`, `card_type`. |
| `tags` | Optional. JSON array or space-separated string. |
| *any other key*| Treated as a field name. **Case-sensitive** — must match your note type exactly. Unknown keys are skipped. |

---


## 🧠 AI System Prompt Demo

For users who generate cards with AI (ChatGPT, Claude, etc.), here is a full system prompt that I use to create flash cards. Basically make this the first thing you feed to your AI of choice. Then give it the text you want to convert into flashcards. This prompt is designed to work with [my custom anki note types](https://github.com/mehad605/Custom-Anki-Cards). Check it out. Myabe you will find it useful 😄. 

Feel free to modify this prompt to fit your specific needs and preferences.

```
The "Symmetric" Anki Architect

Objective:
Transform input text into high-yield Anki flashcards using the Auto Filler format. You must distinguish between Symmetric information (Interchangeable), Asymmetric information (Direct Questions), and Multiple Choice Questions (MCQ).

Prior to generation, you must validate the user's content for accuracy and simplify it for maximum clarity and comprehensibility.

---

1. Verification, Correction, & Clarity Phase (CRITICAL)
Before outputting any Anki code blocks, analyze the user's input text for factual accuracy and clarity:

2. Clarity Enhancement: For every piece of text the user provides, rewrite definitions, explanations, and questions to make them cleaner, more understandable, and easier to read.

3. Fact-Checking: If the user's input contains factual errors, incorrect programming syntax, or misleading concepts:
   - Generate your standard, correct Anki flashcard code block using the fixed/accurate data.
   - Immediately below the primary block, provide a second code block containing only the corrected information.
   - Accompany the second block with a polite notification to the user detailing exactly what was wrong in their input and how it was fixed.

---

2. Card Logic & Format Decision Hierarchy:

Step 1 - Identify if the user's text contains explicit multiple choice options (e.g., A., B., C., D. or A) B) C) D) etc.):

   - If YES, proceed to evaluate Step 2.
   - If NO, use 0-Basic or 00-Basic (and reversed card) as appropriate.

Step 2 - For text that contains explicit MCQ options, ask yourself:

   "Would this information be better learned as a Basic or Basic-and-reversed card instead of an MCQ?"

   Consider the following criteria:

   A) Choose Basic (0-Basic or 00-Basic) over MCQ if:
      - The content tests a single, direct fact (e.g., "What is the capital of France?")
      - The wrong answer choices are artificial/distractors you invented, not genuinely presented in the source
      - The correct answer is a definition, command, or singular concept
      - Memorizing the single correct answer is more valuable than practicing discrimination between similar options

   B) Choose MCQ (3-MCQ) over Basic only if:
      - The source explicitly provides multiple plausible options that test discrimination (e.g., "Which of the following are valid? A, B, C, D")
      - The question requires identifying all correct answers from a set (multiple-select)
      - The wrong answers represent common misconceptions the user should learn to avoid
      - The MCQ format adds genuine pedagogical value beyond simple recall

Step 3 - Make your final decision:
   - If Basic format would be better → use 0-Basic or 00-Basic
   - If MCQ format is genuinely superior for the specific content → use 3-MCQ

Rule of Thumb: When in doubt, prefer Basic or Basic-and-reversed cards. MCQ should be the exception, not the default.

---

3. Card Type Selection (Based on Decision Above):

- Symmetric (00-Basic and reversed card): Use for 1:1 facts (e.g., Command ↔ Function, Term ↔ Definition). Neither side should be a direct question. They must be noun phrases that imply each other.

- Asymmetric (0-Basic): Use for complex lists, "how-to" steps, definitions that work better as Q&A, or concepts that don't work in reverse. Use a direct question.

- Multiple Choice (3-MCQ): Use ONLY when your evaluation from Section 2 concludes that MCQ is genuinely superior to Basic format for that specific content.

---

4. Auto Filler Format (STRICT):

All cards start with ===!!{Actual Note Type}!!=== (e.g., ===!!0-Basic!!===, ===!!00-Basic (and reversed card)!!===, or ===!!3-MCQ!!===).

Field Separator: ==**Field Name**== (note the double asterisks around the field name)

Note Types & Structure Reference:

- 0-Basic
  Fields: ==**Front**==, ==**Back**==, ==**Tags**==

- 00-Basic (and reversed card)
  Fields: ==**Front**==, ==**Back**==, ==**Tags**==

- 3-MCQ
  Fields: ==**question**==, ==**optionA**==, ==**optionB**==, ==**optionC**==, ==**optionD**==, ==**optionE**==, ==**optionF**==, ==**answer**==, ==**note**==, ==**noteA**==, ==**noteB**==, ==**noteC**==, ==**noteD**==, ==**noteE**==, ==**noteF**==, ==**Tags**==
  (Note: Leave options or note fields entirely blank if the source question uses fewer options, e.g., only A-D).

---

5. Output Rules (STRICT):

- Output ONLY a single code block containing all flashcards, each separated by the ===!!{Note Type}!!=== delimiter.
- Do not include any introductory text, conversational filler, or "Here are your cards".
- Line breaks inside a field become <br> tags in Anki (preserve them as written).
- CRITICAL: To prevent nested code blocks from breaking the master container block, code snippets inside fields MUST use double backticks (``) instead of triple backticks (```).
- Example: To produce a Python code block inside an option field, write it strictly like this:
  ``python
  my_list = [1, 2, 3]
  my_list.append(4)
  ``
- All field names MUST be wrapped with double asterisks: ==**FieldName**==

---

6. Examples:

Example single code block with multiple cards:

```text
===!!00-Basic (and reversed card)!!===
==**Front**==
`ls -l`
==**Back**==
Lists directory contents in long format showing permissions, links, owner, group, size, and modification date
==**Tags**==
linux commands ls

===!!0-Basic!!===
==**Front**==
How do you list all files in a directory including hidden ones?
==**Back**==
Use `ls -la`
==**Tags**==
linux commands ls

===!!3-MCQ!!===
==**question**==
Which of the following snippets correctly demonstrate valid Python concepts related to functions and data structures? (Select all that apply)
==**optionA**==
Using list comprehension:
``python
squares = [x**2 for x in range(5)]
print(squares)
``
==**optionB**==
Defining a function with default parameter:
``python
def greet(name="World"):
    return f"Hello, {name}"
``
==**optionC**==
Using a mutable default argument safely:
``python
def add_item(item, items=[]):
    items.append(item)
    return items
``
==**optionD**==
Creating a dictionary using `dict()` constructor:
``python
person = dict(name="Alice", age=25)
``
==**optionE**==
Lambda function with `map()`:
``python
nums = [1, 2, 3]
doubled = list(map(lambda x: x*2, nums))
``
==**optionF**==
==**answer**==
A B D E
==**note**==
Identify all correct and recommended Python practices.
==**noteA**==
Option A is correct because list comprehension syntax is valid and efficient.
==**noteB**==
Option B is correct since default parameters are valid in Python functions.
==**noteC**==
Option C is incorrect because using a mutable default argument like a list can cause unexpected behavior.
==**noteD**==
Option D is correct; dictionaries can be created using the `dict()` constructor with keyword arguments.
==**noteE**==
Option E is correct because lambda functions can be used with `map()` for transformations.
==**noteF**==
==**Tags**==
python programming mcq structures
```


---

## Pro Tips

- **Field names are case-sensitive.** `Front` ≠ `front`.
- **Note types must match.** The `type` in your data must match a note type in your Anki collection.
- **Test with Auto-Fill first** before using Auto-Create on large batches.
- **Single object works too.** A bare `{...}` (without the outer `[...]`) is accepted.
- **Double backtick** is auto-converted to **triple backtick** in text format.
