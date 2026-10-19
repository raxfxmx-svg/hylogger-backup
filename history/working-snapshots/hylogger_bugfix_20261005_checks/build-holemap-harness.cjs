const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const frontend = path.resolve(__dirname, '../hylogger_bugfix_20261005/frontend');
const swc = require(path.join(frontend, 'node_modules/next/dist/build/swc'));
const original = process.argv.includes('--original');
const source = original
  ? execFileSync('git', ['show', 'HEAD:frontend/components/HoleMap.jsx'], { cwd: frontend, encoding: 'utf8' })
  : fs.readFileSync(path.join(frontend, 'components/HoleMap.jsx'), 'utf8');
const code = swc.transformSync(source, {
  jsc: { parser: { syntax: 'ecmascript', jsx: true }, transform: { react: { runtime: 'classic' } }, target: 'es2020' },
  module: { type: 'commonjs' },
}).code;
const script = code => '<script>' + code.replace(/<\/script/gi, '<\\/script') + '</script>';
const harness = fs.readFileSync(path.join(__dirname, 'holemap-harness.js'), 'utf8');
const html = '<!doctype html><html><head><meta charset="utf-8"><title>HoleMap regression</title></head><body><div id="root"></div>' +
  script(fs.readFileSync(path.join(frontend, 'node_modules/react/umd/react.development.js'), 'utf8')) +
  script(fs.readFileSync(path.join(frontend, 'node_modules/react-dom/umd/react-dom.development.js'), 'utf8')) +
  script(harness + '\n' + code + '\nwindow.runRegression(exports.default);') + '</body></html>';
const output = path.join(__dirname, original ? 'holemap-original-regression.html' : 'holemap-regression.html');
fs.writeFileSync(output, html);
console.log(output);
