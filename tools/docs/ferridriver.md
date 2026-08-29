# ferridriver

**Usage**: Drives Chromium, Firefox and WebKit behind one Playwright-shaped API,
and runs TypeScript or Gherkin suites without Node.

## MCP

`install.sh` registers `ferridriver mcp`, so the browser tools arrive in the
session carrying their own instructions. Use those to drive a live page. The CLI
below covers what a live session does not.

## CLI

```bash
ferridriver doctor       # config found, extensions loadable, browsers installed
ferridriver install      # download the browser binaries
ferridriver test         # run *.test.ts / *.spec.ts
ferridriver bdd          # the same runner over .feature files
ferridriver run x.ts     # one-off script with Playwright-shaped bindings
ferridriver codegen      # record a session and emit it as a test
ferridriver trace        # open, print, or list what a run recorded
ferridriver config       # which files layered, and where each value came from
ferridriver upgrade      # replace this binary with the newest release
```

`doctor` is the first thing to run when a session will not start: it checks the
config, the extensions, the instance commands and the browser cache in one pass.
