import { EditorView } from '@codemirror/view'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'

// Themed through CSS variables, so one theme serves light and dark.
const base = EditorView.theme({
  '&': { backgroundColor: 'var(--surface)', color: 'var(--fg)' },
  '.cm-content': { caretColor: 'var(--accent)' },
  '.cm-tooltip': { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px' },
  '.cm-panels': { background: 'var(--surface-2)', color: 'var(--fg)' },
  '.cm-searchMatch': { backgroundColor: 'color-mix(in oklab, var(--warning) 30%, transparent)' },
})
const hl = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.operatorKeyword], color: 'var(--accent)' },
  { tag: [t.string, t.special(t.string)], color: 'var(--success)' },
  { tag: [t.number, t.bool, t.null, t.atom], color: 'var(--warning)' },
  { tag: [t.comment, t.lineComment, t.blockComment], color: 'var(--fg-subtle)', fontStyle: 'italic' },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: 'var(--info)' },
  { tag: [t.typeName, t.className, t.tagName], color: 'var(--accent-soft-fg)', fontWeight: '500' },
  { tag: [t.attributeName, t.propertyName], color: 'var(--fg-muted)' },
  { tag: [t.definition(t.variableName)], color: 'var(--fg)' },
  { tag: [t.punctuation, t.bracket, t.angleBracket], color: 'var(--fg-subtle)' },
])
export const cmTheme = [base, syntaxHighlighting(hl)]
