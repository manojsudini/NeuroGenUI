"""Deterministic IR -> React compiler.

Produces a runnable Vite project (React 18.3.1) and a single-script `preview` for the in-browser runtime.
One reusable component per IR type, one component per page, a useState router, and event handlers that
call src/runtime/actions.js. Every rendered node carries data-ngid / data-ngtype for validation.
"""
from __future__ import annotations

import json
import re

from . import ir as irm

COMPONENT_FOR = {
    "page": "Page", "container": "Container", "card": "Card", "form": "Form", "header": "Header",
    "navbar": "Navbar", "nav_item": "NavItem", "heading": "Heading", "text": "Text", "link": "Link",
    "button": "Button", "input": "Field", "textarea": "TextArea", "checkbox": "Checkbox", "radio": "Radio",
    "select": "Select", "image": "Image", "list": "List", "divider": "Divider", "icon": "Icon",
}
STACK_USERS = {"Page", "Container", "Card", "Form", "Header", "Navbar", "List"}
TEXT_TYPES = {"heading", "text", "link", "nav_item", "icon"}
SELF_ALIGNED = {"button", "image", "link", "checkbox", "radio", "icon", "nav_item"}
ALIGN_SELF = {"left": "flex-start", "center": "center", "right": "flex-end"}
FONT_STACK = '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'

# --------------------------------------------------------------------------- static sources

STORE_JS = """\
import { createContext, useContext, useState } from "react";

export const UIContext = createContext(null);

export function useUI() {
  return useContext(UIContext);
}

/** All UI state of the generated app: current page, field values, messages and visibility. */
export function useUIStore(initialPage, initiallyHidden) {
  const [page, setPage] = useState(initialPage);
  const [values, setValues] = useState({});
  const [messages, setMessages] = useState({});
  const [hidden, setHidden] = useState(initiallyHidden);
  const [texts, setTexts] = useState({});
  const [invalid, setInvalid] = useState({});
  const [notice, setNotice] = useState(null);

  return {
    page,
    values,
    messages,
    invalid,
    notice,
    /** A confirmation shown right before navigating is carried over to the new page as a notice (the owner is unmounted). */
    navigate(pageId, carry) {
      setPage(pageId);
      setMessages({});
      setInvalid({});
      setNotice(carry || null);
    },
    setValue(id, value) {
      setValues((current) => ({ ...current, [id]: value }));
      setInvalid((current) => ({ ...current, [id]: false }));
    },
    showMessage(owner, text, tone) {
      setMessages((current) => ({ ...current, [owner]: { text, tone } }));
    },
    clearMessage(owner) {
      setMessages((current) => ({ ...current, [owner]: null }));
    },
    markInvalid(ids) {
      setInvalid((current) => ({ ...current, ...Object.fromEntries(ids.map((id) => [id, true])) }));
    },
    toggle(id) {
      setHidden((current) => ({ ...current, [id]: !current[id] }));
    },
    setText(id, text) {
      setTexts((current) => ({ ...current, [id]: text }));
    },
    isHidden: (id) => Boolean(hidden[id]),
    textOf: (id, fallback) => texts[id] ?? fallback,
  };
}

/** Attributes every generated element carries, plus the shared UI store. */
export function useNode(id, type) {
  const ui = useUI();
  const attrs = { "data-ngid": id, "data-ngtype": type, hidden: ui.isHidden(id) || undefined };
  return { ui, attrs };
}
"""

ACTIONS_JS = """\
const FORMATS = {
  email: /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/,
  phone: /^\\+?[\\d\\s()-]{7,}$/,
  number: /^-?\\d+(\\.\\d+)?$/,
};

function isEmpty(value) {
  return value === undefined || value === null || value === false || String(value).trim() === "";
}

/**
 * Run an event's actions in order. A failing validation shows its message
 * (role="alert", data-ngmsg=owner) and stops the chain.
 */
export function runActions(owner, actions, ui) {
  ui.clearMessage(owner);
  let carry = null;
  for (const action of actions) {
    switch (action.type) {
      case "validate_required": {
        const missing = action.targets.filter((id) => isEmpty(ui.values[id]));
        if (missing.length > 0) {
          ui.markInvalid(missing);
          ui.showMessage(owner, action.message, "error");
          return false;
        }
        break;
      }
      case "validate_format": {
        const value = String(ui.values[action.target] ?? "").trim();
        if (!FORMATS[action.format].test(value)) {
          ui.markInvalid([action.target]);
          ui.showMessage(owner, action.message, "error");
          return false;
        }
        break;
      }
      case "show_message":
        ui.showMessage(owner, action.text, action.tone || "info");
        carry = { owner, text: action.text, tone: action.tone || "info" };
        break;
      case "navigate":
        ui.navigate(action.page, carry);
        carry = null;
        break;
      case "toggle_visibility":
        ui.toggle(action.target);
        break;
      case "set_text":
        ui.setText(action.target, action.text);
        break;
      default:
        console.warn(`Unknown action: ${action.type}`);
    }
  }
  return true;
}
"""

COMPONENTS: dict[str, str] = {
    "Stack": """\
import { useNode } from "../runtime/store.js";

/** Flex container shared by pages, cards, forms, headers, navbars and plain containers. */
export default function Stack({ id, type, as: Tag = "div", layout = {}, geometry = false, style, children, onSubmit, onClick }) {
  const { attrs } = useNode(id, type);
  const { direction = "column", gap = 12, align = "stretch", justify = "start" } = layout;
  const className = `ng-${type} ng-stack ng-stack--${direction} ng-align-${align} ng-justify-${justify}${geometry ? " ng-geo" : ""}`;
  const handleSubmit = onSubmit
    ? (event) => {
        event.preventDefault();
        onSubmit(event);
      }
    : (event) => event.preventDefault();

  return (
    <Tag
      {...attrs}
      className={className}
      style={{ gap, ...style, cursor: onClick ? "pointer" : undefined }}
      onSubmit={Tag === "form" ? handleSubmit : undefined}
      onClick={onClick}
    >
      {children}
    </Tag>
  );
}
""",
    "Page": """\
import Stack from "./Stack.jsx";

export default function Page(props) {
  return <Stack {...props} type="page" as="main" />;
}
""",
    "Container": """\
import Stack from "./Stack.jsx";

export default function Container(props) {
  return <Stack {...props} type="container" as="section" />;
}
""",
    "Card": """\
import Stack from "./Stack.jsx";

export default function Card(props) {
  return <Stack {...props} type="card" as="section" />;
}
""",
    "Form": """\
import Stack from "./Stack.jsx";

export default function Form(props) {
  return <Stack {...props} type="form" as="form" />;
}
""",
    "Header": """\
import Stack from "./Stack.jsx";

export default function Header(props) {
  return <Stack {...props} type="header" as="header" />;
}
""",
    "Navbar": """\
import Stack from "./Stack.jsx";

export default function Navbar(props) {
  return <Stack {...props} type="navbar" as="nav" />;
}
""",
    "List": """\
import { useNode } from "../runtime/store.js";

export default function List({ id, items = [], layout = {}, style, children }) {
  const { attrs } = useNode(id, "list");
  return (
    <div {...attrs} className="ng-list" style={{ gap: layout.gap ?? 8, ...style }}>
      {items.length > 0 && (
        <ul className="ng-list__items">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {children}
    </div>
  );
}
""",
    "NavItem": """\
import { useNode } from "../runtime/store.js";

export default function NavItem({ id, label, targetPage, style, onClick }) {
  const { ui, attrs } = useNode(id, "nav_item");
  const active = targetPage && ui.page === targetPage;
  const handleClick = (event) => {
    event.preventDefault();
    onClick?.(event);
  };

  return (
    <a {...attrs} href="#" className={active ? "ng-nav-item is-active" : "ng-nav-item"} style={style} onClick={handleClick}>
      {ui.textOf(id, label)}
    </a>
  );
}
""",
    "Heading": """\
import { useNode } from "../runtime/store.js";

export default function Heading({ id, label, level = 2, style }) {
  const { ui, attrs } = useNode(id, "heading");
  const Tag = `h${level}`;
  return (
    <Tag {...attrs} className={`ng-heading ng-heading--${level}`} style={style}>
      {ui.textOf(id, label)}
    </Tag>
  );
}
""",
    "Text": """\
import { useNode } from "../runtime/store.js";

export default function Text({ id, label, style }) {
  const { ui, attrs } = useNode(id, "text");
  return (
    <p {...attrs} className="ng-text" style={style}>
      {ui.textOf(id, label)}
    </p>
  );
}
""",
    "Link": """\
import { useNode } from "../runtime/store.js";

export default function Link({ id, label, style, onClick }) {
  const { ui, attrs } = useNode(id, "link");
  const handleClick = (event) => {
    event.preventDefault();
    onClick?.(event);
  };

  return (
    <a {...attrs} href="#" className="ng-link" style={style} onClick={handleClick}>
      {ui.textOf(id, label)}
    </a>
  );
}
""",
    "Button": """\
import { useNode } from "../runtime/store.js";

export default function Button({ id, label, variant = "primary", size = "md", type = "button", style, onClick }) {
  const { ui, attrs } = useNode(id, "button");
  return (
    <button {...attrs} type={type} className={`ng-btn ng-btn--${variant} ng-btn--${size}`} style={style} onClick={onClick}>
      {ui.textOf(id, label)}
    </button>
  );
}
""",
    "Field": """\
import { useNode } from "../runtime/store.js";

export default function Field({ id, label, inputType = "text", placeholder, required = false, name, style, onChange }) {
  const { ui, attrs } = useNode(id, "input");
  const controlId = `${id}-control`;
  const handleChange = (event) => {
    ui.setValue(id, event.target.value);
    onChange?.(event);
  };

  return (
    <div {...attrs} className="ng-field" style={style}>
      {label && (
        <label htmlFor={controlId} className="ng-field__label">
          {ui.textOf(id, label)}
          {required && <span className="ng-field__required">*</span>}
        </label>
      )}
      <input
        id={controlId}
        name={name || id}
        type={inputType}
        className="ng-input"
        placeholder={placeholder}
        aria-invalid={ui.invalid[id] || undefined}
        value={ui.values[id] ?? ""}
        onChange={handleChange}
      />
    </div>
  );
}
""",
    "TextArea": """\
import { useNode } from "../runtime/store.js";

export default function TextArea({ id, label, placeholder, rows = 4, required = false, style, onChange }) {
  const { ui, attrs } = useNode(id, "textarea");
  const controlId = `${id}-control`;
  const handleChange = (event) => {
    ui.setValue(id, event.target.value);
    onChange?.(event);
  };

  return (
    <div {...attrs} className="ng-field" style={style}>
      {label && (
        <label htmlFor={controlId} className="ng-field__label">
          {ui.textOf(id, label)}
          {required && <span className="ng-field__required">*</span>}
        </label>
      )}
      <textarea
        id={controlId}
        className="ng-input ng-textarea"
        rows={rows}
        placeholder={placeholder}
        aria-invalid={ui.invalid[id] || undefined}
        value={ui.values[id] ?? ""}
        onChange={handleChange}
      />
    </div>
  );
}
""",
    "Select": """\
import { useNode } from "../runtime/store.js";

export default function Select({ id, label, options = [], required = false, style, onChange }) {
  const { ui, attrs } = useNode(id, "select");
  const controlId = `${id}-control`;
  const handleChange = (event) => {
    ui.setValue(id, event.target.value);
    onChange?.(event);
  };

  return (
    <div {...attrs} className="ng-field" style={style}>
      {label && (
        <label htmlFor={controlId} className="ng-field__label">
          {ui.textOf(id, label)}
          {required && <span className="ng-field__required">*</span>}
        </label>
      )}
      <select id={controlId} className="ng-input ng-select" value={ui.values[id] ?? ""} onChange={handleChange}>
        <option value="">Select…</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}
""",
    "Checkbox": """\
import { useNode } from "../runtime/store.js";

export default function Checkbox({ id, label, checked = false, style, onChange }) {
  const { ui, attrs } = useNode(id, "checkbox");
  const value = ui.values[id] ?? checked;
  const handleChange = (event) => {
    ui.setValue(id, event.target.checked);
    onChange?.(event);
  };

  return (
    <label {...attrs} className="ng-check" style={style}>
      <input type="checkbox" checked={value} onChange={handleChange} />
      <span>{ui.textOf(id, label)}</span>
    </label>
  );
}
""",
    "Radio": """\
import { useNode } from "../runtime/store.js";

export default function Radio({ id, label, group = "options", checked = false, style, onChange }) {
  const { ui, attrs } = useNode(id, "radio");
  const groupKey = `group:${group}`;
  const selected = ui.values[groupKey] === undefined ? checked : ui.values[groupKey] === id;
  const handleChange = (event) => {
    ui.setValue(groupKey, id);
    ui.setValue(id, true);
    onChange?.(event);
  };

  return (
    <label {...attrs} className="ng-check" style={style}>
      <input type="radio" name={group} checked={selected} onChange={handleChange} />
      <span>{ui.textOf(id, label)}</span>
    </label>
  );
}
""",
    "Image": """\
import { useNode } from "../runtime/store.js";

const PHOTO_BASE = window.NGUI_PHOTO_BASE || "/photos/";

export default function Image({ id, alt, photo, style }) {
  const { attrs } = useNode(id, "image");
  if (!photo) {
    return (
      <div {...attrs} className="ng-image ng-image--placeholder" role="img" aria-label={alt || "Image"} style={style}>
        <svg viewBox="0 0 24 24" width="36" height="36" aria-hidden="true">
          <path d="M4 5h16v14H4z M4 16l5-5 4 4 3-3 4 4" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </div>
    );
  }
  return <img {...attrs} className="ng-image" src={`${PHOTO_BASE}${photo}.jpg`} alt={alt || photo} style={style} />;
}
""",
    "Divider": """\
import { useNode } from "../runtime/store.js";

export default function Divider({ id, style }) {
  const { attrs } = useNode(id, "divider");
  return <hr {...attrs} className="ng-divider" style={style} />;
}
""",
    "Icon": """\
import { useNode } from "../runtime/store.js";

export default function Icon({ id, label, style, onClick }) {
  const { attrs } = useNode(id, "icon");
  return (
    <span {...attrs} className="ng-icon" role="img" aria-label={label || "icon"} style={style} onClick={onClick}>
      {label ? label.slice(0, 1).toUpperCase() : "●"}
    </span>
  );
}
""",
    "Message": """\
import { useUI } from "../runtime/store.js";

/** Feedback shown by an element's event handler (validation errors, confirmations). */
export default function Message({ owner }) {
  const ui = useUI();
  const message = ui.messages[owner];
  if (!message) {
    return null;
  }
  return (
    <div className={`ng-msg ng-msg--${message.tone}`} role={message.tone === "error" ? "alert" : "status"} data-ngmsg={owner}>
      {message.text}
    </div>
  );
}
""",
}

STYLES_CSS = """\
:root {
  --ng-primary: __PRIMARY__;
  --ng-radius: __RADIUS__px;
  --ng-font: __FONT__;
  --ng-text: #18181b;
  --ng-muted: #63636e;
  --ng-border: #e4e4e7;
  --ng-surface: #ffffff;
  --ng-canvas: #f6f6f8;
  --ng-danger: #dc2626;
  --ng-success: #15803d;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--ng-canvas);
  color: var(--ng-text);
  font-family: var(--ng-font);
  font-size: 15px;
  line-height: 1.5;
}

[hidden] {
  display: none !important;
}

.ng-app {
  min-height: 100vh;
  padding: 32px 24px;
}

.ng-stack {
  display: flex;
  min-width: 0;
}

.ng-stack--column {
  flex-direction: column;
}

.ng-stack--row {
  flex-direction: row;
  flex-wrap: wrap;
}

.ng-stack--row > * {
  flex: 1 1 0;
  min-width: 0;
}

.ng-stack--row > .ng-btn,
.ng-stack--row > .ng-link,
.ng-stack--row > .ng-nav-item,
.ng-stack--row > .ng-check,
.ng-stack--row > .ng-icon,
.ng-stack--row > .ng-heading,
.ng-stack--row > .ng-msg {
  flex: 0 0 auto;
}

/* Layout that follows the sketch: rows stay side by side, children keep drawn widths. */
.ng-geo.ng-stack--row {
  flex-wrap: nowrap;
}

@media (max-width: 640px) {
  .ng-geo.ng-stack--row {
    flex-wrap: wrap;
  }

  .ng-geo > * {
    width: 100% !important;
    margin-left: 0 !important;
  }
}

.ng-align-start { align-items: flex-start; }
.ng-align-center { align-items: center; }
.ng-align-end { align-items: flex-end; }
.ng-align-stretch { align-items: stretch; }
.ng-justify-start { justify-content: flex-start; }
.ng-justify-center { justify-content: center; }
.ng-justify-end { justify-content: flex-end; }
.ng-justify-between { justify-content: space-between; }

.ng-stack--column > .ng-btn,
.ng-stack--column > .ng-link,
.ng-stack--column > .ng-check,
.ng-stack--column > .ng-icon {
  align-self: flex-start;
}

.ng-page {
  width: 100%;
  max-width: 1080px;
  margin: 0 auto;
}

.ng-card {
  background: var(--ng-surface);
  border: 1px solid var(--ng-border);
  border-radius: calc(var(--ng-radius) + 4px);
  padding: 24px;
  box-shadow: 0 1px 2px rgba(24, 24, 27, 0.04), 0 8px 24px rgba(24, 24, 27, 0.06);
}

.ng-form {
  background: var(--ng-surface);
  border: 1px solid var(--ng-border);
  border-radius: calc(var(--ng-radius) + 4px);
  padding: 24px;
}

.ng-card .ng-form,
.ng-form .ng-form {
  border: 0;
  padding: 0;
}

.ng-container {
  min-width: 0;
}

.ng-header,
.ng-navbar {
  background: var(--ng-surface);
  border: 1px solid var(--ng-border);
  border-radius: var(--ng-radius);
  padding: 12px 18px;
}

.ng-heading {
  margin: 0;
  line-height: 1.2;
  letter-spacing: -0.01em;
}

.ng-heading--1 { font-size: 30px; font-weight: 700; }
.ng-heading--2 { font-size: 24px; font-weight: 700; }
.ng-heading--3 { font-size: 19px; font-weight: 600; }
.ng-heading--4 { font-size: 16px; font-weight: 600; }

.ng-text {
  margin: 0;
  color: var(--ng-muted);
}

.ng-link,
.ng-nav-item {
  color: var(--ng-primary);
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
}

.ng-link:hover {
  text-decoration: underline;
}

.ng-nav-item {
  color: var(--ng-text);
  padding: 6px 10px;
  border-radius: calc(var(--ng-radius) - 2px);
}

.ng-nav-item:hover,
.ng-nav-item.is-active {
  background: var(--ng-canvas);
  color: var(--ng-primary);
}

.ng-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: var(--ng-radius);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s ease, background 0.15s ease;
}

.ng-btn--sm { padding: 6px 12px; font-size: 13px; }
.ng-btn--md { padding: 10px 18px; font-size: 15px; }
.ng-btn--lg { padding: 14px 24px; font-size: 17px; }

.ng-btn--primary {
  background: var(--ng-primary);
  color: #ffffff;
}

.ng-btn--secondary {
  background: var(--ng-canvas);
  border-color: var(--ng-border);
  color: var(--ng-text);
}

.ng-btn--outline {
  background: transparent;
  border-color: var(--ng-primary);
  color: var(--ng-primary);
}

.ng-btn--ghost {
  background: transparent;
  color: var(--ng-primary);
}

.ng-btn--danger {
  background: var(--ng-danger);
  color: #ffffff;
}

.ng-btn:hover {
  filter: brightness(0.94);
}

.ng-btn:focus-visible,
.ng-input:focus-visible,
.ng-link:focus-visible {
  outline: 2px solid var(--ng-primary);
  outline-offset: 2px;
}

.ng-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.ng-field__label {
  font-size: 13px;
  font-weight: 600;
}

.ng-field__required {
  color: var(--ng-danger);
  margin-left: 2px;
}

.ng-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--ng-border);
  border-radius: var(--ng-radius);
  background: var(--ng-surface);
  color: inherit;
  font: inherit;
}

.ng-input[aria-invalid="true"] {
  border-color: var(--ng-danger);
}

.ng-textarea {
  flex: 1;
  resize: vertical;
}

.ng-check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.ng-check input {
  width: 16px;
  height: 16px;
  accent-color: var(--ng-primary);
}

.ng-image {
  display: block;
  width: 100%;
  height: 200px;
  object-fit: cover;
  border-radius: var(--ng-radius);
}

.ng-image--placeholder {
  display: grid;
  place-items: center;
  background: #ececf0;
  color: #9a9aa5;
}

.ng-divider {
  width: 100%;
  height: 1px;
  border: 0;
  padding: 0;
  box-sizing: content-box;
  background: var(--ng-border);
  background-clip: content-box;
  margin: 4px 0;
}

.ng-icon {
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--ng-canvas);
  color: var(--ng-primary);
  font-weight: 700;
}

.ng-list {
  display: flex;
  flex-direction: column;
}

.ng-list__items {
  margin: 0;
  padding-left: 20px;
}

.ng-msg {
  padding: 10px 12px;
  border-radius: var(--ng-radius);
  font-size: 14px;
  font-weight: 500;
}

.ng-toast {
  position: fixed;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 50;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}
.ng-msg--error { background: #fef2f2; color: var(--ng-danger); }
.ng-msg--success { background: #f0fdf4; color: var(--ng-success); }
.ng-msg--info { background: #eff6ff; color: #1d4ed8; }
"""

INDEX_HTML = """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>__TITLE__</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""

MAIN_JSX = """\
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);
"""

VITE_CONFIG = """\
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
"""

README_MD = """\
# __TITLE__

Generated by NeuroGenUI from a sketch and voice instructions (version __VERSION__).

```bash
npm install
npm run dev
```

- `src/pages/` one component per page, `src/components/` reusable UI components,
- `src/runtime/actions.js` the event actions (validation, messages, navigation),
- `src/runtime/store.js` the UI state (current page, field values, messages).
"""


# --------------------------------------------------------------------------- helpers

def _camel(text: str) -> str:
    return "".join(part.capitalize() for part in re.findall(r"[A-Za-z0-9]+", text))


def _const(text: str) -> str:
    return "_".join(re.findall(r"[A-Za-z0-9]+", text)).upper()


def _js(value) -> str:
    """Python value -> JS literal (JSON is valid JS)."""
    return json.dumps(value, ensure_ascii=False)


def _js_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z_]\w*", key) else _js(key)


def _attr(name: str, value) -> str | None:
    if value is None or value is False or value == "" or value == {} or value == []:
        return None
    if value is True:
        return name
    if isinstance(value, str):
        if re.search(r'["{}\\\n<>]', value):
            return f"{name}={{{_js(value)}}}"
        return f'{name}="{value}"'
    if isinstance(value, dict):
        body = ", ".join(f"{_js_key(k)}: {_js(v)}" for k, v in value.items())
        return f"{name}={{{{ {body} }}}}"
    return f"{name}={{{_js(value)}}}"


def _tag(component: str, attrs: list[str], indent: int, children: list[str] | None = None) -> list[str]:
    pad = " " * indent
    attrs = [a for a in attrs if a]
    one_line = f"<{component}{''.join(' ' + a for a in attrs)}"
    if len(pad) + len(one_line) <= 100:
        head = [pad + one_line]
    else:
        head = [pad + f"<{component}"] + [pad + "  " + a for a in attrs]
    if children is None:
        if len(head) == 1:
            return [head[0] + " />"]
        return head + [pad + "/>"]
    if len(head) == 1:
        return [head[0] + ">", *children, pad + f"</{component}>"]
    return head + [pad + ">", *children, pad + f"</{component}>"]


def node_style(node: dict) -> dict:
    """IR style keys -> React inline style object (variant/size become component props instead)."""
    style, out = node.get("style", {}), {}
    node_type = node["type"]
    color = style.get("color")
    if color:
        if node_type == "button":
            out["background"] = color
            out["borderColor"] = color
            if style.get("variant") in ("outline", "ghost"):
                out["background"] = "transparent"
                out["color"] = color
        elif node_type in irm.CONTAINER_TYPES:
            out["borderColor"] = color
        else:
            out["color"] = color
    if style.get("textColor"):
        out["color"] = style["textColor"]
    if style.get("bg"):
        out["background"] = style["bg"]
    width = style.get("width")
    if width == "full":
        out["width"] = "100%"
        if node_type in SELF_ALIGNED:
            out["alignSelf"] = "stretch"
    elif isinstance(width, int):
        if node_type == "page":
            out["maxWidth"] = width
        else:
            out["width"] = width
            out["maxWidth"] = "100%"
    if isinstance(style.get("height"), int):
        out["height"] = style["height"]
    align = style.get("align")
    if align in ALIGN_SELF:
        if node_type in TEXT_TYPES:
            out["textAlign"] = align
            if node_type in ("heading", "text") and align != "left":
                out["alignSelf"] = ALIGN_SELF[align]  # shrink to the text so it sits where it was drawn
        if node_type in SELF_ALIGNED or (node_type == "image" and width != "full"):
            out["alignSelf"] = ALIGN_SELF[align]
    if isinstance(style.get("fontSize"), int):
        out["fontSize"] = style["fontSize"]
    if style.get("fontWeight"):
        out["fontWeight"] = style["fontWeight"]
    if isinstance(style.get("radius"), int):
        out["borderRadius"] = style["radius"]
    if node_type == "image" and isinstance(width, int) and "height" not in out:
        out["height"] = "auto"
    return out


STACK_DEFAULTS = {"direction": "column", "gap": 12, "align": "stretch", "justify": "start"}


def _layout_overrides(layout: dict) -> dict:
    """Only the layout values that differ from Stack's defaults, to keep the JSX short."""
    return {k: v for k, v in layout.items() if k in STACK_DEFAULTS and STACK_DEFAULTS[k] != v}



# --------------------------------------------------------------------------- geometry-aware layout

NATURAL_WIDTH = {"checkbox", "radio", "icon"}
GROWING_TEXT = {"heading", "text", "link", "nav_item"}
CONTAINER_PADDED = {"card", "form", "header", "navbar"}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pct(value: float) -> str:
    return f"{round(value * 100, 1):g}%"


class Geometry:
    """Turns the sketch geometry stored in the IR (bbox per node + meta.frame) into responsive layout:
    percentage widths and offsets inside the parent's drawn frame, vertical spacing proportional to the
    drawing, drawn heights for images/buttons/boxes. Explicit user styles always win."""

    def __init__(self, ir: dict, safe_ids: set[str]):
        meta = ir.get("meta", {})
        self.frame = meta.get("frame")
        self.moved = set(meta.get("moved", [])) | set(meta.get("free_layout", []))
        self.safe_ids = safe_ids

    def box(self, node: dict) -> dict | None:
        if not self.frame or node["id"] in self.moved or node["id"] in self.safe_ids:
            return None
        return node.get("bbox")

    def frame_box(self, node: dict, is_root: bool) -> dict | None:
        """The drawn frame a container's children are laid out in (None = no geometry)."""
        if not self.frame:
            return None
        box = self.frame.get("content") if is_root else self.box(node)
        if not box or box["w"] <= 0 or not any(self.box(c) for c in node.get("children", [])):
            return None
        return box

    def px(self, dy: float) -> float:
        """Normalised sketch height -> CSS px."""
        return dy * self.frame["sketch_height"] * self.frame["scale"]

    def page_style(self) -> dict:
        return {"maxWidth": self.frame["page_width"]} if self.frame else {}

    @staticmethod
    def line_row(children: list[dict], parent_type: str = "") -> bool:
        """A row of similar-height items drawn on one line (menu, buttons): centre them vertically.
        A horizontal navbar/header is one line by definition."""
        if parent_type in ("navbar", "header"):
            return True
        heights = [c["bbox"]["h"] for c in children if c.get("bbox")]
        return bool(heights) and max(heights) <= 2.5 * min(heights) and \
            not any(c["type"] in irm.CONTAINER_TYPES or c["type"] == "image" for c in children)

    def child_style(self, child: dict, frame: dict, direction: str, cursor: float,
                    frame_children: list[dict] | None = None, parent_type: str = "") -> tuple[dict, float]:
        """Style placing `child` inside `frame`; cursor = bottom (column) or right edge (row) so far."""
        b = self.box(child)
        if b is None:
            return ({"marginTop": 12} if direction == "column" else {"marginLeft": 12}), cursor
        user = child.get("style", {})
        out: dict = {}
        offset = (b["x"] - (frame["x"] if direction == "column" else cursor)) / frame["w"]
        width = b["w"] / frame["w"]
        if user.get("width") == "full":
            if direction == "row":
                out["flex"] = "1 1 0"
        elif user.get("width") is None and child["type"] in GROWING_TEXT:
            out["minWidth"] = _pct(min(width, 1.0))  # at least the drawn width; longer text grows, never clips
            out["maxWidth"] = "100%"
        elif user.get("width") is None and child["type"] not in NATURAL_WIDTH:
            out["width"] = "100%" if width >= 0.97 else _pct(width)
        if direction == "row" and "flex" not in out:
            # drawn boxes of misdetected/overlapping siblings can add up to more than the row; percentage-sized children may shrink
            # (never overflow into the neighbouring box), natural-width ones keep their size
            out["flex"] = "0 1 auto" if "width" in out else "0 0 auto"
            if "width" in out:
                out["minWidth"] = 40
        if user.get("width") is None and user.get("align") is None and offset > 0.005:
            # a child drawn near the right edge of a narrow parent must still fit inside it: natural-width items (labels, checkboxes)
            # keep room for their text, otherwise the offset pushes them over their neighbours
            frame_px = max(frame["w"] * self.frame["sketch_width"] * self.frame["scale"], 1.0)
            natural = min(1.0, (28 + 8 * len(child.get("label") or "")) / frame_px)
            reserve = width if "width" in out else max(width, natural)
            offset = min(offset, max(0.0, 1.0 - min(reserve, 1.0)))
            if offset > 0.005:
                out["marginLeft"] = _pct(offset)
        if direction == "column":
            out["marginTop"] = round(_clamp(self.px(b["y"] - cursor), 0, 160))
            cursor = max(cursor, b["y"] + b["h"])
            if out.get("width", "100%") != "100%" or "minWidth" in out:
                out["alignSelf"] = "flex-start"
        else:
            if not self.line_row(frame_children or [], parent_type):
                out["marginTop"] = round(_clamp(self.px(b["y"] - frame["y"]), 0, 80))
            cursor = b["x"] + b["w"]  # items of a one-line row (a menu, a button bar) are centred by the row
        height = self.px(b["h"])
        kind = child["type"]
        if kind == "image" and user.get("height") is None:
            out["height"] = round(_clamp(height, 40, 600))
        elif kind == "button" and user.get("height") is None and height > 30:
            out["height"] = round(_clamp(height, 32, 64))
        elif kind == "heading" and user.get("fontSize") is None and user.get("size") is None:
            out["fontSize"] = round(_clamp(height * 0.62, 16, 44))
        elif kind == "textarea" and child.get("props", {}).get("rows"):
            pass  # explicit rows decide the height
        elif kind in ("text", "textarea", "list") or kind in irm.CONTAINER_TYPES:
            out["minHeight"] = round(_clamp(height, 0, 600 if kind != "text" else 120))
        elif kind in ("checkbox", "radio", "link", "nav_item") and user.get("height") is None:
            # small controls take the drawn row height, so the rows below keep their drawn offsets
            out["minHeight"] = round(_clamp(height, 0, 80))
        elif kind == "icon" and user.get("height") is None:
            size = round(_clamp(height, 16, 38))  # stays under the 40 px mark that separates an icon from a picture
            out["width"], out["height"] = size, size
        elif kind == "divider" and user.get("height") is None:
            out["paddingTop"] = out["paddingBottom"] = round(_clamp((height - 1) / 2, 0, 40))
        return out, cursor

    def container_style(self, node: dict, frame: dict, bottom: float, is_root: bool) -> dict:
        """Padding of a drawn box: the drawn inset comes from the children's offsets instead."""
        if is_root or node["type"] not in CONTAINER_PADDED and node["type"] != "container":
            return {}
        inset = round(_clamp(self.px(frame["y"] + frame["h"] - bottom), 0, 80))
        return {"padding": 0, "paddingBottom": inset} if node["type"] in CONTAINER_PADDED else {"paddingBottom": inset}

# --------------------------------------------------------------------------- page compiler

class _PageCompiler:
    def __init__(self, page: dict, safe_ids: set[str], geometry: Geometry):
        self.page = page
        self.safe_ids = safe_ids
        self.geo = geometry
        self.used: set[str] = set()
        self.handlers: list[tuple[str, str, str, list]] = []  # (handler name, const name, owner, actions)
        self.uses_message = False

    def handler_for(self, node: dict, on: str) -> str | None:
        if node["id"] in self.safe_ids:
            return None
        event = next((e for e in node.get("events", []) if e.get("on") == on and e.get("actions")), None)
        if event is None:
            return None
        name = f"handle{_camel(node['id'])}{on.capitalize()}"
        const = f"{_const(node['id'])}_{on.upper()}"
        self.handlers.append((name, const, node["id"], event["actions"]))
        return name

    def emit(self, node: dict, indent: int, in_submit_form: bool = False, placement: dict | None = None) -> list[str]:
        component = COMPONENT_FOR.get(node["type"], "Container")
        self.used.add(component)
        safe = node["id"] in self.safe_ids
        props = node.get("props", {})
        style = {} if safe else {**(placement or {}), **node_style(node)}
        node_style_flags = node.get("style", {})
        attrs = [_attr("id", node["id"])]
        node_type = node["type"]
        owns_message = False

        if node_type in irm.CONTAINER_TYPES:
            if node_type == "list":
                attrs.append(_attr("items", props.get("items")))
            is_root = node is self.page["root"]
            layout = dict(node.get("layout") or {})
            frame = None if safe else self.geo.frame_box(node, is_root)
            submit = self.handler_for(node, "submit") if node_type == "form" else None
            click = self.handler_for(node, "click")
            children = []
            direction = layout.get("direction", "column")
            cursor = (frame["y"] if direction == "column" else frame["x"]) if frame else 0.0
            bottom = frame["y"] if frame else 0.0
            for child in node.get("children", []):
                placement = None
                if frame:
                    placement, cursor = self.geo.child_style(child, frame, direction, cursor, node["children"], node_type)
                    if child.get("bbox"):
                        bottom = max(bottom, child["bbox"]["y"] + child["bbox"]["h"])
                children.extend(self.emit(child, indent + 2, in_submit_form or bool(submit), placement))
            if frame:
                layout["gap"] = 0
                layout["justify"] = "start"  # drawn offsets position the children
                if direction == "row":
                    layout["align"] = "center" if self.geo.line_row(node["children"], node_type) else "start"
                style = {**self.geo.container_style(node, frame, bottom, is_root), **style}
            if is_root and not safe:
                style = {**self.geo.page_style(), **style}
            attrs.append(_attr("layout", _layout_overrides(layout)))
            attrs.append(_attr("geometry", bool(frame)))
            attrs.append(_attr("style", style))
            attrs.append(f"onSubmit={{{submit}}}" if submit else None)
            attrs.append(f"onClick={{{click}}}" if click else None)
            if submit or click:
                children.extend(self._message(node["id"], indent + 2))
            return _tag(component, attrs, indent, children)

        if node_type not in ("image", "divider"):
            attrs.append(_attr("label", node.get("label") or None))
        if node_type == "heading":
            attrs.append(_attr("level", props.get("level", 2)))
        elif node_type == "button":
            variant = node_style_flags.get("variant")
            attrs.append(_attr("variant", variant if variant and variant != "primary" else None))
            if in_submit_form and not node.get("events"):
                attrs.append(_attr("type", "submit"))
        elif node_type in ("input", "textarea", "select"):
            if node_type == "input":
                input_type = props.get("inputType", "text")
                attrs.append(_attr("inputType", input_type if input_type != "text" else None))
            attrs.append(_attr("placeholder", props.get("placeholder")))
            if node_type == "textarea":
                attrs.append(_attr("rows", props.get("rows")))
            if node_type == "select":
                attrs.append(_attr("options", props.get("options") or []))
            attrs.append(_attr("required", bool(props.get("required"))))
        elif node_type in ("checkbox", "radio"):
            if node_type == "radio":
                attrs.append(_attr("group", props.get("group")))
            attrs.append(_attr("checked", bool(props.get("checked"))))
        elif node_type == "image":
            attrs.append(_attr("photo", props.get("photo")))
            attrs.append(_attr("alt", props.get("alt") or node.get("label") or None))
        elif node_type == "nav_item":
            attrs.append(_attr("targetPage", props.get("href_page")))
        if node_type in ("button",) and node_style_flags.get("size") not in (None, "md"):
            attrs.append(_attr("size", node_style_flags["size"]))
        attrs.append(_attr("style", style))
        for on, prop in (("click", "onClick"), ("change", "onChange")):
            handler = self.handler_for(node, on)
            if handler:
                attrs.append(f"{prop}={{{handler}}}")
                owns_message = True
        lines = _tag(component, attrs, indent)
        if owns_message:
            lines.extend(self._message(node["id"], indent))
        return lines

    def _message(self, owner: str, indent: int) -> list[str]:
        self.uses_message = True
        return [" " * indent + f'<Message owner="{owner}" />']

    def compile(self) -> tuple[str, str]:
        name = f"{_camel(self.page['name']) or 'Main'}Page"
        body = self.emit(self.page["root"], 4)
        if self.uses_message:
            self.used.add("Message")
        imports = []
        if self.handlers:
            imports.append('import { useUI } from "../runtime/store.js";')
            imports.append('import { runActions } from "../runtime/actions.js";')
        for component in sorted(self.used):
            imports.append(f'import {component} from "../components/{component}.jsx";')
        consts = []
        for _, const, _, actions in self.handlers:
            consts.append(f"const {const} = {json.dumps(actions, indent=2, ensure_ascii=False)};")
        lines = imports + [""]
        if consts:
            lines += ["\n\n".join(consts), ""]
        lines.append(f"export default function {name}() {{")
        if self.handlers:
            lines.append("  const ui = useUI();")
            for handler, const, owner, _ in self.handlers:
                lines.append(f'  const {handler} = () => runActions("{owner}", {const}, ui);')
            lines.append("")
        lines.append("  return (")
        lines.extend(body)
        lines.append("  );")
        lines.append("}")
        return name, "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- public API

def _component_closure(used: set[str]) -> list[str]:
    names = set(used)
    if names & STACK_USERS:
        names.add("Stack")
    order = ["Stack", *[c for c in COMPONENTS if c != "Stack"]]
    return [c for c in order if c in names]


def _initially_hidden(ir: dict) -> dict:
    return {n["id"]: True for n, _, _ in irm.walk(ir) if n.get("style", {}).get("hidden")}


def _app_jsx(pages: list[tuple[dict, str]], hidden: dict) -> str:
    lines = ['import { UIContext, useUIStore } from "./runtime/store.js";']
    for _, name in pages:
        lines.append(f'import {name} from "./pages/{name}.jsx";')
    lines += ["", "const PAGES = {"]
    for page, name in pages:
        lines.append(f"  {page['id']}: {name},")
    lines.append("};")
    lines.append("")
    lines.append(f"const INITIALLY_HIDDEN = {json.dumps(hidden)};")
    first_page, first_name = pages[0]
    lines += [
        "",
        "export default function App() {",
        f'  const ui = useUIStore("{first_page["id"]}", INITIALLY_HIDDEN);',
        f"  const CurrentPage = PAGES[ui.page] ?? {first_name};",
        "",
        "  return (",
        "    <UIContext.Provider value={ui}>",
        '      <div className="ng-app">',
        "        <CurrentPage />",
        "        {ui.notice && (",
        '          <div className={`ng-msg ng-msg--${ui.notice.tone} ng-toast`} role="status" data-ngmsg={ui.notice.owner}>',
        "            {ui.notice.text}",
        "          </div>",
        "        )}",
        "      </div>",
        "    </UIContext.Provider>",
        "  );",
        "}",
    ]
    return "\n".join(lines) + "\n"


def _styles(ir: dict) -> str:
    theme = ir.get("meta", {}).get("theme", {})
    primary = theme.get("primary") or irm.DEFAULT_PRIMARY
    if not re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-z]+|rgba?\([^;{}]*\)", str(primary)):
        primary = irm.DEFAULT_PRIMARY
    radius = int(theme.get("radius", 10)) if str(theme.get("radius", 10)).isdigit() else 10
    font = theme.get("font") or "Inter"
    font_stack = FONT_STACK if font == "Inter" else f'"{re.sub(r"[^A-Za-z0-9 -]", "", font)}", ' + FONT_STACK
    return (STYLES_CSS.replace("__PRIMARY__", str(primary)).replace("__RADIUS__", str(radius))
            .replace("__FONT__", font_stack))


def _package_json(title: str) -> str:
    package = {
        "name": re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-") or "neurogenui-app",
        "private": True,
        "version": "1.0.0",
        "type": "module",
        "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
        "dependencies": {"react": "18.3.1", "react-dom": "18.3.1"},
        "devDependencies": {"@vitejs/plugin-react": "^4.3.4", "vite": "^5.4.11"},
    }
    return json.dumps(package, indent=2) + "\n"


def _to_script(source: str) -> str:
    """Strip ES module syntax so a file can live in the single preview script."""
    out = []
    for line in source.splitlines():
        if line.startswith("import "):
            continue
        line = re.sub(r"^export default function ", "function ", line)
        line = re.sub(r"^export (function|const|let) ", r"\1 ", line)
        out.append(line)
    return "\n".join(out).strip("\n")


def generate_code(ir: dict, safe_ids: set[str] | None = None, version: int | None = None) -> dict:
    """IR -> {"files", "preview", "stats"}. Deterministic: the same IR always yields the same code."""
    safe_ids = set(safe_ids or ())
    title = ir.get("meta", {}).get("title") or "NeuroGenUI app"
    pages, page_files, used = [], {}, set()
    geometry = Geometry(ir, safe_ids)
    seen_names: set[str] = set()
    for page in ir.get("pages", []):
        compiler = _PageCompiler(page, safe_ids, geometry)
        name, source = compiler.compile()
        while name in seen_names:
            name = name.replace("Page", "") + "2Page"
            source = re.sub(r"export default function \w+\(", f"export default function {name}(", source)
        seen_names.add(name)
        pages.append((page, name))
        page_files[f"src/pages/{name}.jsx"] = source
        used |= compiler.used
    components = _component_closure(used)
    styles = _styles(ir)
    app = _app_jsx(pages, _initially_hidden(ir))

    files = {
        "package.json": _package_json(title),
        "index.html": INDEX_HTML.replace("__TITLE__", title.replace("<", "")),
        "vite.config.js": VITE_CONFIG,
        "README.md": README_MD.replace("__TITLE__", title).replace("__VERSION__", str(version or "")),
        "src/main.jsx": MAIN_JSX,
        "src/App.jsx": app,
        "src/styles.css": styles,
        "src/runtime/store.js": STORE_JS,
        "src/runtime/actions.js": ACTIONS_JS,
    }
    for component in components:
        files[f"src/components/{component}.jsx"] = COMPONENTS[component]
    files.update(page_files)

    preview_parts = [
        f"// NeuroGenUI preview: {title}",
        "const { createContext, useContext, useState } = React;",
        "",
        "(function injectStyles(css) {",
        "  const style = document.createElement(\"style\");",
        "  style.setAttribute(\"data-ngui\", \"app\");",
        "  style.textContent = css;",
        "  document.head.appendChild(style);",
        "})(" + _js(styles) + ");",
        "",
        _to_script(STORE_JS),
        "",
        _to_script(ACTIONS_JS),
    ]
    for component in components:
        preview_parts += ["", _to_script(COMPONENTS[component])]
    for _, name in pages:
        preview_parts += ["", _to_script(page_files[f"src/pages/{name}.jsx"])]
    preview_parts += ["", _to_script(app), "", 'ReactDOM.createRoot(document.getElementById("root")).render(<App />);', ""]
    preview = "\n".join(preview_parts)

    source_files = [p for p in files if p.startswith("src/")]
    stats = {
        "files": len(files),
        "components": len(components),
        "pages": len(pages),
        "loc": sum(files[p].count("\n") for p in source_files),
        "preview_bytes": len(preview.encode()),
    }
    return {"files": files, "preview": preview, "stats": stats}


def photos_used(ir: dict) -> set[str]:
    return {n["props"]["photo"] for n in irm.nodes(ir, "image") if n.get("props", {}).get("photo") in irm.PHOTO_KEYS}
