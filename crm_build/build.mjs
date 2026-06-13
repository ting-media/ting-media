// Build script: precompile the CRM's inline JSX so the browser doesn't run Babel on every load.
// Source of truth: ../live_index.html (editable, with <script type="text/babel">)
// Output:          ../index.compiled.html (deploy this to the VPS as index.html)
import { readFileSync, writeFileSync } from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const Babel = require('@babel/standalone');

const SRC = new URL('../live_index.html', import.meta.url);
const OUT = new URL('../index.compiled.html', import.meta.url);

let html = readFileSync(SRC, 'utf8');

const openTag = '<script type="text/babel">';
const start = html.indexOf(openTag);
if (start === -1) throw new Error('text/babel script tag not found');
const bodyStart = start + openTag.length;
const end = html.lastIndexOf('</script>');
if (end <= bodyStart) throw new Error('closing </script> not found after babel script');

const jsx = html.slice(bodyStart, end);
console.log('JSX size:', (jsx.length / 1024).toFixed(0), 'KB');

const t0 = Date.now();
const { code } = Babel.transform(jsx, {
  presets: ['react'],
  sourceType: 'script',
  compact: true,
  comments: false,
});
console.log('compiled in', Date.now() - t0, 'ms; JS size:', (code.length / 1024).toFixed(0), 'KB');

// Never allow a literal </script> inside the inline script
const safe = code.replace(/<\/script/gi, '<\\/script');

html = html.slice(0, start) + '<script>\n' + safe + '\n</script>' + html.slice(end + '</script>'.length);

// Drop the in-browser Babel runtime — no longer needed
html = html.replace(/^\s*<script src="https:\/\/unpkg\.com\/@babel\/standalone\/babel\.min\.js"><\/script>\s*$/m, '');

writeFileSync(OUT, html, 'utf8');
console.log('wrote', OUT.pathname, (html.length / 1024).toFixed(0), 'KB');
