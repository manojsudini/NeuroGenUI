# NeuroGenUI evaluation dataset

**This dataset is synthetic.** The sketches are hand-drawn *in style*, rendered by a program, not drawn
by people. The voice commands are real speech audio, but it is synthesized by a text-to-speech model, not
recorded from people. Ground truth is exact by construction because the labels come from the same
specification the images are rendered from. Every label file carries `"synthetic": true`.

## Contents

| Item | Count | Where |
|---|---|---|
| UI sketches (PNG, 1000 px wide, 560–814 px tall) | 40 (4 per category × 10 categories) | `sketches/<id>.png` |
| Ground-truth labels | 40 | `labels/<id>.json` |
| Labelled components | 490 | inside the labels |
| Specified interactions (functional ground truth) | 58 | `labels/*.json → interactions` |
| Instruction-derived requirements | 407 | `labels/*.json → requirements` |
| Voice refinement commands | 80 (10 per category × 8 categories) | `commands/commands.jsonl` |
| Command audio (MP3, OpenAI TTS) | 80 | `commands/audio/cmd_XXX.mp3` |

### Sketches per category

| Category | Sketch ids | Components |
|---|---|---|
| login | login_01–04 | 32 |
| registration | reg_01–04 | 38 |
| dashboard | dash_01–04 | 63 |
| profile | prof_01–04 | 42 |
| ecommerce | shop_01–04 | 58 |
| banking | bank_01–04 | 50 |
| booking | book_01–04 | 48 |
| contact | contact_01–04 | 50 |
| settings | set_01–04 | 42 |
| landing | land_01–04 | 67 |

### Components by type

heading 92 · text 61 · button 61 · input 57 · nav_item 42 · card 37 · image 33 · checkbox 15 · radio 15 ·
icon 14 · navbar 14 · select 14 · link 9 · list 7 · divider 7 · header 6 · textarea 5 · form 1.

Layouts: 22 desktop, 15 mobile (narrow centred column), 3 medium-width forms. Render variety: 3 handwriting
fonts (Patrick Hand 17, Architects Daughter 14, Caveat 9) and 2 pen styles (grainy pencil 22, ink pen 18).

### Commands per category

| Category | n | Post-condition kinds used |
|---|---|---|
| add | 10 | `all`(node_exists + order), node_exists |
| remove | 10 | removed |
| modify | 10 | label_changed, attr_contains |
| move | 10 | order (below / above / left_of) |
| resize | 10 | size_change (area / width / height / font) |
| style | 10 | style_eq (colour hue) |
| interaction | 10 | event (validate_required / validate_format / show_message) |
| navigation | 10 | navigates |

All 7 example commands from brief §4.4 are included verbatim (`"brief_example": true`): cmd_001 (create),
cmd_002 (forgot-password link), cmd_003 (phone field), cmd_011 (remove the image), cmd_031 (move the button),
cmd_051 (make the login button blue) and cmd_061 (error on empty fields). The 80 commands reference 35 of the
40 sketches. Phrasing varies on purpose, with indirect forms such as "the sign in button should be a bit bigger",
"We don't need the Buy now button anymore" and "Can the date field go below the time slots?".

## How it was generated

```
python dataset/tools/make_sketches.py      # sketches/ + labels/   (deterministic, about 20 s)
python dataset/tools/make_commands.py      # commands/commands.jsonl (validates every target against the labels)
python dataset/tools/make_audio.py         # commands/audio/*.mp3 via OpenAI TTS (needs OPENAI_API_KEY in project/.env)
```

Use the evaluation venv (`evaluation/.venv`) or any Python with numpy, Pillow, python-dotenv and openai.

### Sketches (`tools/specs.py` + `tools/make_sketches.py`)

1. **Specification.** `specs.py` defines the 40 screens by hand as component trees: navbars (horizontal and
   sidebar), headers, cards, forms, rows/columns, stat cards, product grids, image placeholders, charts,
   radio and checkbox groups, toggles, selects, text areas, lists, links, dividers, icons and multiple buttons.
   Each screen also has an `instruction` (the spoken description given to the generate step, naming the
   components and their behaviour) and `interactions` (the behaviours the instruction asks for).
2. **Layout.** A small flex-like engine (columns, weighted rows, packed navbars) assigns every component a
   box on a 1000 px wide frame.
3. **Hand-drawn rendering** (2× supersampled, then downsampled):
   - Strokes are resampled polylines displaced along the normal by low-frequency drift (two random-phase
     sines plus a random walk) and jitter. Line ends overshoot or fall short, lines bow slightly, and pen
     width varies along the stroke (pressure).
   - Rectangles are rotated by about ±0.9° and drawn either as four separate strokes with offset corners or as
     one continuous (rounded) stroke that does not quite close. Secondary buttons are double-stroked.
   - Text uses OFL handwriting fonts (`tools/fonts/`, downloaded from the google/fonts GitHub repository, with
     licences included), with per-glyph rotation and a wandering baseline.
   - Paragraphs are wavy scribbles, images are X-crossed boxes (or mountain-and-sun / line-chart doodles,
     or circles for avatars), radios are circles, checkboxes are small squares, toggles are pills, selects
     have a chevron and search/date inputs have small glyphs.
   - The paper is off-white with Gaussian noise, low-frequency blotches and specks. The ink is
     black/blue/grey, about 55% are grainy pencil, and some sketches get a slight blur.
4. **Determinism.** The RNG seed is `sha256(id)`, so re-running the generator reproduces identical files.

### Label format (`labels/<id>.json`, contract §6 plus extras)

```jsonc
{
  "id": "login_03", "category": "login", "title": "Welcome back", "synthetic": true,
  "generator": "make_sketches.py v1", "seed_source": "sha256('login_03')",
  "render": {"font": "Caveat.ttf", "tool": "pen", "layout": "mobile"},
  "width": 1000, "height": 698,
  "instruction": "A centered sign in card: a user icon, the heading Welcome back, ...",
  "components": [                       // pre-order; parent = index of the enclosing drawn container
    {"type": "card", "label": "", "bbox": {"x": 0.23, "y": 0.08, "w": 0.48, "h": 0.83}, "parent": null},
    {"type": "input", "label": "Password", "bbox": {...}, "parent": 0, "props": {"inputType": "password"}},
    ...
  ],
  "interactions": [ {"event": "click", "target_label": "Sign in", "expect": {"type": "validate_required"}},
                    {"event": "click", "target_label": "Create an account", "expect": {"type": "navigate", "page": "Register"}} ],
  "requirements": [ {"kind": "node_exists", "type": "input", "label_contains": "Password"},
                    {"kind": "input_type", "label_contains": "Password", "input_type": "password"},
                    {"kind": "interaction", "event": "click", "target_label": "Sign in", "expect": {...}} ]
}
```

- `bbox` is normalised to the sketch frame (x/1000, y/height). For an input the box is the drawn field, with
  its label written inside. For a checkbox or radio the box covers the glyph and its label text.
- `label` is the visible text. It is empty for scribbled paragraphs, images, icons, dividers and containers.
- `props` (optional) add `level`, `inputType`, `options`, `items`, `alt`, `shape`, `toggle` where they apply.
- `expect.type` is one of `validate_required`, `validate_format` (`field_label`, `format`), `show_message`
  (`text_contains`) and `navigate` (`page`).
- `requirements` are derived automatically. There is one `node_exists` for every labelled interactive or
  heading component the instruction names, an `input_type` for named email/password/date/number/tel fields,
  a `count_at_least` image check when the instruction mentions an image, and one `interaction` per stated behaviour.

### Commands (`commands/commands.jsonl`)

```jsonc
{"id": "cmd_031", "category": "move", "sketch_id": "login_02", "text": "Move the button below the password field.",
 "expected": {"op": "move", "target_ref": "Log In", "target_label": "Log In", "target_type": "button",
              "params": {"relation": "below", "anchor": "Password"}},
 "check": {"kind": "order", "first": {"label": "Password", "type": "input"},
           "then": {"label": "Log In", "type": "button"}, "relation": "below"},
 "base": "generated", "brief_example": true, "audio": "audio/cmd_031.mp3",
 "tts": {"model": "tts-1", "voice": "alloy", "format": "mp3", ...}}
```

- `base`: `generated` means the command is applied to the UI generated from the sketch. `empty` (only the
  create command) means it is applied to a blank page.
- `check` kinds are `node_exists`, `removed`, `label_changed`, `attr_contains`, `order`, `size_change`,
  `style_eq` (coarse hue of the computed colour), `event`, `navigates` and `all`. They are evaluated on the
  rendered DOM by `evaluation/checks.py`, identically for the pipeline and the baseline.
- `make_commands.py` refuses to write the file if any target or anchor label is missing from the sketch's labels.

### Audio

The audio comes from OpenAI TTS model `tts-1` (`gpt-4o-mini-tts` was not available on the project key),
in MP3 format. Voices rotate over alloy, echo, fable, onyx, nova and shimmer (13–14 commands each). The voice used per command is
stored in `commands/audio_meta.json` and in the `tts` field of each command. During evaluation the audio is
transcribed by Whisper (`whisper-1`), so speech recognition is exercised on real audio.

## Limitations

- Synthetic sketches are cleaner and more consistent than real user drawings. There is no perspective, no
  crossed-out strokes, no overlapping annotations and no real photographs of paper. Detection results on
  real sketches are expected to be lower.
- TTS speech is clear, studio-quality and accent-neutral, so Whisper WER here is a lower bound for real users.
- Labels follow one annotation convention (for example, input labels are written inside the box). Other
  conventions are not covered.
