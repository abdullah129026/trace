"use strict";
/* One-shot JavaScript tracer for the Trace sandbox.

 * Spawned by app/sandbox.py (node subprocess, scrubbed env, rlimits, wall
 * timeout). Reads one JSON request from stdin, prints one Trace JSON to
 * stdout. Never imported anywhere else.
 *
 * Approach (ADR-002): parse with acorn, instrument statement boundaries
 * with step callbacks, run in a vm context with no require/process/fs/
 * network. v1 is synchronous only: async/yield is a clean error, not a
 * hang.
 */

const vm = require("vm");
const acorn = require("acorn");

const TRUNCATED_KEY = "__trace_truncated__";
const STEP_LIMIT = { __trace_step_limit: true }; // identity-compared, never serialized
const FRAME_TRUNCATED = "<frames truncated>";

function readRequest() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => {
      try {
        resolve(JSON.parse(data));
      } catch (e) {
        reject(e);
      }
    });
    process.stdin.on("error", reject);
  });
}

/* ------------------------------------------------------------------ */
/* AST walking                                                         */
/* ------------------------------------------------------------------ */

function walk(node, visitors, parent) {
  if (!node || typeof node.type !== "string") return;
  if (visitors.enter) visitors.enter(node, parent || null);
  for (const key of Object.keys(node)) {
    if (key === "start" || key === "end" || key === "loc") continue;
    const child = node[key];
    if (Array.isArray(child)) {
      for (const c of child) if (c && typeof c.type === "string") walk(c, visitors, node);
    } else if (child && typeof child.type === "string") {
      walk(child, visitors, node);
    }
  }
  if (visitors.leave) visitors.leave(node, parent || null);
}

function patternNames(pattern, out) {
  if (!pattern) return;
  switch (pattern.type) {
    case "Identifier":
      out.push(pattern.name);
      break;
    case "ObjectPattern":
      for (const prop of pattern.properties) {
        if (prop.type === "Property") patternNames(prop.value, out);
        else patternNames(prop.argument, out); // RestElement
      }
      break;
    case "ArrayPattern":
      for (const el of pattern.elements) patternNames(el, out);
      break;
    case "RestElement":
      patternNames(pattern.argument, out);
      break;
    case "AssignmentPattern":
      patternNames(pattern.left, out);
      break;
  }
}

const FUNCTION_TYPES = new Set(["FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"]);

/* Pass 1: scopes, declared names, and v1 capability checks. */
function analyze(program) {
  const scopeOf = new Map(); // function-or-program node -> Set(names)
  const declared = new Set();
  const stack = [];
  let hasAsync = false;
  let hasModuleSyntax = false;

  const addNames = (names) => {
    const scope = stack[stack.length - 1];
    for (const n of names) {
      scope.add(n);
      declared.add(n);
    }
  };

  walk(program, {
    enter(node) {
      if (node.type === "Program") {
        const scope = new Set();
        scopeOf.set(node, scope);
        stack.push(scope);
        return;
      }
      if (FUNCTION_TYPES.has(node.type)) {
        if (node.async) hasAsync = true;
        if (node.id && node.id.name) addNames([node.id.name]); // visible in enclosing scope
        const scope = new Set();
        for (const param of node.params) {
          const names = [];
          patternNames(param, names);
          for (const n of names) {
            scope.add(n);
            declared.add(n);
          }
        }
        scopeOf.set(node, scope);
        stack.push(scope);
        return;
      }
      if (node.type === "AwaitExpression" || node.type === "YieldExpression") hasAsync = true;
      if (
        node.type === "ImportDeclaration" ||
        node.type === "ExportNamedDeclaration" ||
        node.type === "ExportDefaultDeclaration" ||
        node.type === "ExportAllDeclaration"
      ) {
        hasModuleSyntax = true;
      }
      if (node.type === "VariableDeclaration") {
        const names = [];
        for (const d of node.declarations) patternNames(d.id, names);
        addNames(names);
      }
      if (node.type === "ClassDeclaration" && node.id) addNames([node.id.name]);
      if (node.type === "CatchClause" && node.param) {
        const names = [];
        patternNames(node.param, names);
        addNames(names);
      }
    },
    leave(node) {
      if (node.type === "Program" || FUNCTION_TYPES.has(node.type)) stack.pop();
    },
  });

  return { scopeOf, declared, hasAsync, hasModuleSyntax };
}

/* ------------------------------------------------------------------ */
/* Instrumentation                                                     */
/* ------------------------------------------------------------------ */

const LOOP_TYPES = new Set(["WhileStatement", "DoWhileStatement", "ForStatement", "ForInStatement", "ForOfStatement"]);

const INSTRUMENTED_STATEMENTS = new Set([
  "ExpressionStatement",
  "IfStatement",
  "ForStatement",
  "ForInStatement",
  "ForOfStatement",
  "WhileStatement",
  "DoWhileStatement",
  "SwitchStatement",
  "ReturnStatement",
  "ThrowStatement",
  "TryStatement",
  "BreakStatement",
  "ContinueStatement",
  "DebuggerStatement",
  "VariableDeclaration",
  "FunctionDeclaration",
  "ClassDeclaration",
  "WithStatement",
  "LabeledStatement",
]);

/* A step call spliced before `if (x) foo();` would steal the if body, so
 * unbraced single-statement bodies get wrapped in braces first. */
function needsBraces(node, parent) {
  if (!parent || node.type === "BlockStatement") return false;
  if (parent.type === "IfStatement") return parent.consequent === node || parent.alternate === node;
  if (
    parent.type === "ForStatement" ||
    parent.type === "ForInStatement" ||
    parent.type === "ForOfStatement" ||
    parent.type === "WhileStatement" ||
    parent.type === "WithStatement"
  ) {
    return parent.body === node;
  }
  if (parent.type === "DoWhileStatement" || parent.type === "LabeledStatement") return parent.body === node;
  return false;
}

function functionName(node, parent) {
  if (node.id && node.id.name) return node.id.name;
  if (parent) {
    if (parent.type === "VariableDeclarator" && parent.id.type === "Identifier") return parent.id.name;
    if (
      (parent.type === "Property" || parent.type === "MethodDefinition" || parent.type === "PropertyDefinition") &&
      !parent.computed &&
      parent.key.type === "Identifier"
    ) {
      return parent.key.name;
    }
  }
  return "anonymous";
}

/* Pass 2: insert step calls, enter/exit hooks, and brace wraps. Returns
 * the rewritten source. Insertions are applied back-to-front so offsets
 * from the original AST stay valid. */
function instrument(program, analysis) {
  const { scopeOf, declared } = analysis;

  // Helper names are random per run and checked against declared names, so
  // user code can never shadow or collide with the instrumentation.
  let uid;
  let STEP, ENTER, EXIT;
  do {
    uid = Math.random().toString(36).slice(2, 10);
    STEP = `__ts_${uid}__`;
    ENTER = `__te_${uid}__`;
    EXIT = `__tx_${uid}__`;
  } while (declared.has(STEP) || declared.has(ENTER) || declared.has(EXIT));

  const insertions = [];
  const at = (pos, text) => insertions.push({ pos, text });
  const scopes = [];

  const visibleNames = () => {
    const names = [];
    for (let i = scopes.length - 1; i >= 0; i--) {
      for (const n of scopes[i]) if (!names.includes(n)) names.push(n);
    }
    return names;
  };

  const pairsText = () =>
    visibleNames()
      .map((n) => `[${JSON.stringify(n)}, () => ${n}]`)
      .join(",");

  walk(program, {
    enter(node, parent) {
      if (node.type === "Program" || FUNCTION_TYPES.has(node.type)) {
        scopes.push(scopeOf.get(node));
        if (FUNCTION_TYPES.has(node.type)) {
          const name = functionName(node, parent);
          const body = node.body;
          if (body.type === "BlockStatement") {
            at(body.start + 1, `${ENTER}(${JSON.stringify(name)});try{`);
            at(body.end - 1, `}finally{${EXIT}();}`);
          } else {
            // Arrow with expression body: () => expr becomes
            // () => { enter; try { return (expr); } finally { exit; } }
            at(body.start, `{${ENTER}(${JSON.stringify(name)});try{return(`);
            at(body.end, `);}finally{${EXIT}();}}`);
          }
        }
        return;
      }
      if (!INSTRUMENTED_STATEMENTS.has(node.type)) return;
      // A `for` init declaration is not a standalone statement; splicing a
      // step call there breaks the grammar. The loop body carries the
      // per-iteration steps instead.
      if (
        node.type === "VariableDeclaration" &&
        parent &&
        (parent.type === "ForStatement" || parent.type === "ForInStatement" || parent.type === "ForOfStatement") &&
        parent.init === node
      ) {
        return;
      }
      // A loop whose body holds no instrumented statement (empty block,
      // lone semicolon) would spin without ever calling the step function,
      // so the step cap could never trip. Force a step into such bodies.
      if (LOOP_TYPES.has(node.type)) {
        const body = node.body;
        const line = node.loc.start.line;
        if (body.type === "EmptyStatement") {
          at(body.start, `{${STEP}(${line}, [${pairsText()}]);`);
          at(body.end, `}`);
        } else if (body.type === "BlockStatement" && !body.body.some((s) => INSTRUMENTED_STATEMENTS.has(s.type))) {
          at(body.start + 1, `${STEP}(${line}, [${pairsText()}]);`);
        }
      }
      const line = node.loc.start.line;
      if (needsBraces(node, parent)) {
        at(node.start, `{${STEP}(${line}, [${pairsText()}]);`);
        at(node.end, `}`);
      } else {
        at(node.start, `${STEP}(${line}, [${pairsText()}]);`);
      }
    },
    leave(node) {
      if (node.type === "Program" || FUNCTION_TYPES.has(node.type)) scopes.pop();
    },
  });

  insertions.sort((a, b) => b.pos - a.pos);
  let code = program.__source;
  for (const { pos, text } of insertions) {
    code = code.slice(0, pos) + text + code.slice(pos);
  }

  // Final "return" step: captures the finished top-level state, mirroring
  // the Python tracer's module-return step. The getters run while top-level
  // bindings are still alive.
  const lines = program.__source.split(/\r?\n/);
  const lastLine = Math.max(1, lines.length);
  const topNames = [...scopeOf.get(program)];
  const topPairs = topNames.map((n) => `[${JSON.stringify(n)}, () => ${n}]`).join(",");
  code += `\n${STEP}(${lastLine}, [${topPairs}], "return");`;

  return { code, STEP, ENTER, EXIT };
}

/* ------------------------------------------------------------------ */
/* Runtime: snapshot, step recording, vm sandbox                       */
/* ------------------------------------------------------------------ */

function snapshotValue(value, caps, depth, seen) {
  if (value === null || value === undefined) return value;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : String(value); // NaN/Infinity are not JSON-safe
  }
  if (typeof value === "string") {
    if (value.length <= caps.snapshotChars) return value;
    return { type: "string", value: value.slice(0, caps.snapshotChars), [TRUNCATED_KEY]: true };
  }
  if (typeof value === "function") {
    const label = value.name ? `[Function ${value.name}]` : "[Function anonymous]";
    return { type: "function", repr: label, [TRUNCATED_KEY]: false };
  }
  if (typeof value !== "object") {
    return { type: typeof value, repr: String(value), [TRUNCATED_KEY]: false }; // bigint, symbol
  }
  if (seen.has(value)) return { type: "object", [TRUNCATED_KEY]: true, circular: true };
  if (depth >= 3) return { type: Array.isArray(value) ? "array" : "object", [TRUNCATED_KEY]: true };
  seen.add(value);

  const child = (v) => snapshotValue(v, caps, depth + 1, seen);
  const cut = (v) => v !== null && typeof v === "object" && v[TRUNCATED_KEY] === true;

  if (Array.isArray(value)) {
    const preview = value.slice(0, caps.previewItems).map(child);
    return {
      type: "array",
      length: value.length,
      preview,
      [TRUNCATED_KEY]: value.length > caps.previewItems || preview.some(cut),
    };
  }
  const keys = Object.keys(value);
  const preview = {};
  for (const k of keys.slice(0, caps.previewItems)) preview[k] = child(value[k]);
  return {
    type: "object",
    length: keys.length,
    preview,
    [TRUNCATED_KEY]: keys.length > caps.previewItems || Object.values(preview).some(cut),
  };
}

function makeTrace(req, steps, result) {
  return {
    version: 1,
    language: "javascript",
    room_id: req.room_id,
    source_lines: req.source.split(/\r?\n/),
    steps,
    result,
  };
}

function errorTrace(req, message) {
  return makeTrace(req, [], { status: "error", steps_captured: 0, truncated: false, error: message });
}

function traceRequest(req) {
  const source = req.source;
  const caps = {
    snapshotChars: req.snapshot_chars || 2000,
    previewItems: req.preview_items || 5,
    maxStdout: req.max_stdout_chars || 50000,
    maxFrames: req.max_stack_frames || 64,
  };
  const maxSteps = req.max_steps || 2000;

  let program;
  try {
    program = acorn.parse(source, { ecmaVersion: "latest", locations: true });
  } catch (e) {
    return errorTrace(req, `SyntaxError: ${e.message}`);
  }
  program.__source = source;

  const analysis = analyze(program);
  if (analysis.hasAsync) {
    return errorTrace(req, "async/await and generators are not supported in Trace v1 (synchronous code only)");
  }
  if (analysis.hasModuleSyntax) {
    return errorTrace(req, "import/export (modules) are not supported in Trace v1; paste a single self-contained snippet");
  }

  const { code, STEP, ENTER, EXIT } = instrument(program, analysis);

  // --- sandboxed runtime state ---
  const steps = [];
  const stack = ["<main>"];
  let depth = 0;
  let stepCount = 0;
  let stdoutBuf = "";

  const formatArg = (a) => {
    if (typeof a === "string") return a;
    if (a === undefined) return "undefined";
    try {
      const j = JSON.stringify(a);
      return j === undefined ? String(a) : j;
    } catch {
      return String(a);
    }
  };

  const sandbox = {
    [STEP]: (line, pairs, event) => {
      stepCount++;
      // The cap exception propagates through user try/finally (exits still
      // fire, so the stack stays accurate). If user code catches it, the
      // vm timeout below is the backstop; the parent wall timeout is the
      // last one. See ADR-002.
      if (stepCount > maxSteps) throw STEP_LIMIT;
      const locals = {};
      for (const [name, getter] of pairs) {
        try {
          locals[name] = snapshotValue(getter(), caps, 0, new Set());
        } catch {
          // TDZ or out-of-scope name: skip it rather than lie about it.
        }
      }
      const frameNames = stack.slice();
      if (depth > caps.maxFrames) frameNames[frameNames.length - 1] = `<${depth - caps.maxFrames} frames truncated>`;
      steps.push({
        i: steps.length,
        line,
        event: event || "line",
        stack: frameNames,
        locals,
        stdout_so_far: stdoutBuf.slice(-caps.maxStdout),
      });
    },
    [ENTER]: (name) => {
      depth++;
      if (depth <= caps.maxFrames) stack.push(name);
      else if (depth === caps.maxFrames + 1) stack.push(FRAME_TRUNCATED);
    },
    [EXIT]: () => {
      if (depth <= caps.maxFrames + 1) stack.pop();
      depth--;
    },
    console: {
      log: (...args) => {
        stdoutBuf += args.map(formatArg).join(" ") + "\n";
      },
    },
    // Deliberately small global surface: no require, process, Buffer,
    // timers, or fetch. Anything else is a ReferenceError, which becomes
    // an honest error trace.
    Math,
    JSON,
    Object,
    Array,
    String,
    Number,
    Boolean,
    Date,
    RegExp,
    Error,
    TypeError,
    RangeError,
    ReferenceError,
    SyntaxError,
    EvalError,
    URIError,
    Map,
    Set,
    WeakMap,
    WeakSet,
    Promise,
    parseInt,
    parseFloat,
    isNaN,
    isFinite,
    Infinity,
    NaN,
    undefined,
  };
  const context = vm.createContext(sandbox);

  // Fires before the parent's wall timeout so the driver can report the
  // timeout as a trace result instead of being SIGKILLed mid-run.
  const vmTimeoutMs = Math.max(100, Math.floor((req.wall_seconds || 10) * 1000 * 0.8));

  try {
    vm.runInContext(code, context, { timeout: vmTimeoutMs });
  } catch (e) {
    if (e === STEP_LIMIT) {
      return makeTrace(req, steps, { status: "truncated", steps_captured: steps.length, truncated: true });
    }
    const message =
      e && e.code === "ERR_SCRIPT_EXECUTION_TIMEOUT"
        ? `execution timed out after ${req.wall_seconds || 10} seconds (wall clock)`
        : `${(e && e.name) || "Error"}: ${(e && e.message) || e}`;
    if (steps.length > 0) {
      // The last recorded step is the pre-execution state at the throw
      // site; mirror it as the exception event.
      const last = steps[steps.length - 1];
      steps.push({ ...last, i: steps.length, event: "exception" });
    }
    return makeTrace(req, steps, { status: "error", steps_captured: steps.length, truncated: false, error: message });
  }

  return makeTrace(req, steps, { status: "ok", steps_captured: steps.length, truncated: false });
}

async function main() {
  const req = await readRequest();
  if (!req.room_id) req.room_id = "LOCAL";
  const trace = traceRequest(req);
  process.stdout.write(JSON.stringify(trace) + "\n");
}

main().catch((e) => {
  process.stderr.write(`driver failure: ${(e && e.message) || e}\n`);
  process.exit(1);
});
