/** Guards the format compatibility note: every target format offered in the
 * selector needs a note, the README link has to resolve, and an unknown
 * format must render nothing instead of "undefined".
 *
 * The frontend is plain browser scripts, so settings-fields.js is evaluated in
 * an empty VM context rather than imported. */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const fieldsSource = read("../js/settings-fields.js");
const panelSource = read("../js/settings-panel.js");
const readme = read("../../README.md");

const sandbox = vm.createContext({});
const { FORMAT_NOTES, formatNote } = vm.runInContext(
  `${fieldsSource}\n;({ FORMAT_NOTES, formatNote });`,
  sandbox
);

/** Target formats the Settings selector offers, in selector order. */
function offeredFormats() {
  const selector = panelSource.match(
    /<select id="set-image-target-format"[\s\S]*?<\/select>/
  );
  assert.ok(selector, "target-format selector not found in settings-panel.js");
  return [...selector[0].matchAll(/<option value="([^"]+)"/g)].map((m) => m[1]);
}

test("every offered target format has a compatibility note", () => {
  const formats = offeredFormats();
  assert.ok(formats.length > 0);
  for (const format of formats) {
    assert.match(
      FORMAT_NOTES[format] ?? "",
      /\S/,
      `no FORMAT_NOTES entry for "${format}"`
    );
  }
});

test("no note is left behind for a format the selector dropped", () => {
  const formats = new Set(offeredFormats());
  for (const format of Object.keys(FORMAT_NOTES)) {
    assert.ok(formats.has(format), `FORMAT_NOTES has a stale "${format}"`);
  }
});

test("notes state lossless vs re-encode and name a viewer", () => {
  for (const format of offeredFormats()) {
    assert.match(FORMAT_NOTES[format], /re-encoded lossily/, `${format} note lacks the pixel effect`);
  }
  // JXL is the only format where a source class survives untouched.
  assert.match(FORMAT_NOTES.jxl, /JPEG sources/);
  assert.doesNotMatch(FORMAT_NOTES.heic, /JPEG sources/);
  assert.doesNotMatch(FORMAT_NOTES.avif, /JPEG sources/);
});

test("formatNote renders the note, a link, and nothing for unknown formats", () => {
  const html = formatNote("jxl");
  assert.match(html, /class="field__hint"/);
  assert.match(html, /href="[^"]*#image-formats"/);
  assert.equal(formatNote("png"), "");
  assert.equal(formatNote(undefined), "");
});

test("the linked README section exists", () => {
  const anchors = [...readme.matchAll(/^#{1,6}\s+(.+)$/gm)].map((m) =>
    m[1]
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .trim()
      .replace(/\s+/g, "-")
  );
  assert.ok(anchors.includes("image-formats"), "README lacks an Image formats section");
});
