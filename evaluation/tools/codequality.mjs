// Static code-quality metrics for generated React code.
// stdin: JSON {"items":[{"key":"...","files":{"path.jsx": "source", ...}}]}
// stdout: JSON {"results":{key:{...metrics}}}
// Metrics per item (aggregated over its .js/.jsx files):
//   parses            all files parse with @babel/parser (jsx)
//   parse_errors      list of messages
//   loc               non-blank, non-comment-only lines
//   components        number of component definitions (Capitalised function / arrow / class returning JSX)
//   usages            number of JSX elements that instantiate a user-defined component
//   reuse_ratio       usages / components
//   max_fn_lines      longest function (lines)
//   functions         number of functions
//   eslint_warnings   eslint messages (recommended + react/recommended + react-hooks), errors included
//   eslint_by_rule    {rule: count}
import { parse } from "@babel/parser";
import traverseMod from "@babel/traverse";
import { ESLint } from "eslint";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import js from "@eslint/js";

const traverse = traverseMod.default || traverseMod;

const eslint = new ESLint({
  overrideConfigFile: true,
  overrideConfig: [
    js.configs.recommended,
    {
      files: ["**/*.{js,jsx}"],
      plugins: { react, "react-hooks": reactHooks },
      languageOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        parserOptions: { ecmaFeatures: { jsx: true } },
        globals: { ...globals.browser, React: "readonly", ReactDOM: "readonly" },
      },
      settings: { react: { version: "18.3" } },
      rules: {
        ...react.configs.recommended.rules,
        ...reactHooks.configs.recommended.rules,
        "react/prop-types": "off",          // generated code has no prop-types by design (both systems)
        "react/react-in-jsx-scope": "off",  // classic runtime with React global
      },
    },
  ],
});

function isJSXReturning(path) {
  let found = false;
  path.traverse({
    JSXElement(p) { found = true; p.stop(); },
    JSXFragment(p) { found = true; p.stop(); },
    Function(p) { if (p !== path) p.skip(); },
  });
  return found;
}

function analyzeSource(src, file) {
  const out = { parses: true, parse_error: null, loc: 0, defs: new Set(), usages: 0, maxFn: 0, functions: 0 };
  out.loc = src.split("\n").filter((l) => { const t = l.trim(); return t && !t.startsWith("//"); }).length;
  let ast;
  try {
    ast = parse(src, { sourceType: "module", plugins: ["jsx"], errorRecovery: false });
  } catch (e) {
    out.parses = false;
    out.parse_error = `${file}: ${e.message}`;
    return out;
  }
  const usageNames = [];
  traverse(ast, {
    Function(path) {
      out.functions += 1;
      const n = path.node;
      const lines = n.loc ? n.loc.end.line - n.loc.start.line + 1 : 0;
      if (lines > out.maxFn) out.maxFn = lines;
      let name = n.id && n.id.name;
      if (!name && path.parentPath.isVariableDeclarator()) name = path.parentPath.node.id.name;
      if (name && /^[A-Z]/.test(name) && isJSXReturning(path)) out.defs.add(name);
    },
    ClassDeclaration(path) {
      const name = path.node.id && path.node.id.name;
      if (name && /^[A-Z]/.test(name)) out.defs.add(name);
    },
    JSXOpeningElement(path) {
      const nm = path.node.name;
      if (nm.type === "JSXIdentifier" && /^[A-Z]/.test(nm.name)) usageNames.push(nm.name);
      if (nm.type === "JSXMemberExpression") usageNames.push(nm.object.name + "." + nm.property.name);
    },
  });
  out.usageNames = usageNames;
  return out;
}

async function analyzeItem(files) {
  const res = { parses: true, parse_errors: [], loc: 0, components: 0, usages: 0, reuse_ratio: null,
                max_fn_lines: 0, functions: 0, eslint_warnings: 0, eslint_by_rule: {}, files: 0 };
  const defs = new Set();
  const usageNames = [];
  for (const [path, src] of Object.entries(files)) {
    if (!/\.(jsx?|mjs)$/.test(path)) continue;
    res.files += 1;
    const a = analyzeSource(src, path);
    res.loc += a.loc;
    if (!a.parses) { res.parses = false; res.parse_errors.push(a.parse_error); continue; }
    a.defs.forEach((d) => defs.add(d));
    usageNames.push(...a.usageNames);
    res.max_fn_lines = Math.max(res.max_fn_lines, a.maxFn);
    res.functions += a.functions;
    const lint = await eslint.lintText(src, { filePath: path.endsWith(".js") ? path.replace(/\.js$/, ".jsx") : path });
    for (const m of lint[0].messages) {
      res.eslint_warnings += 1;
      const r = m.ruleId || (m.fatal ? "parse" : "other");
      res.eslint_by_rule[r] = (res.eslint_by_rule[r] || 0) + 1;
    }
  }
  res.components = defs.size;
  res.usages = usageNames.filter((n) => defs.has(n)).length;
  res.reuse_ratio = defs.size ? +(res.usages / defs.size).toFixed(3) : null;
  return res;
}

let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", async () => {
  const { items } = JSON.parse(input);
  const results = {};
  for (const it of items) results[it.key] = await analyzeItem(it.files);
  process.stdout.write(JSON.stringify({ results }));
});
