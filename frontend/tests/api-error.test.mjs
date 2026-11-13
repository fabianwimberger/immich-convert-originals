/** Guards the message an API failure surfaces: FastAPI's validation errors are a
 * list of objects, and handing that list to an Error used to show
 * "[object Object]" under the Save button.
 *
 * The frontend is a plain browser script, so api.js is evaluated in an empty VM
 * context rather than imported. */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../js/api.js", import.meta.url), "utf8");
const sandbox = vm.createContext({ fetch: () => {} });
const { _handle } = vm.runInContext(`${source}\n;({ _handle });`, sandbox);

const response = (body, status = 422) => ({
  ok: false,
  status,
  json: async () => body,
});

test("validation errors read as their messages", async () => {
  const err = await _handle(
    response({
      detail: [
        {
          type: "less_than_equal",
          loc: ["body", "image_quality_heic"],
          msg: "Input should be less than or equal to 100",
        },
      ],
    }),
    "/settings",
    "PUT"
  ).catch((e) => e);

  assert.equal(err.message, "Input should be less than or equal to 100");
  assert.equal(err.status, 422);
});

test("several validation errors are joined", async () => {
  const err = await _handle(
    response({
      detail: [
        { loc: ["body", "video_crf"], msg: "Input should be an integer" },
        { loc: ["body", "concurrency"], msg: "Input should be at least 1" },
      ],
    }),
    "/settings",
    "PUT"
  ).catch((e) => e);

  assert.equal(
    err.message,
    "Input should be an integer; Input should be at least 1"
  );
});

test("a string detail is used as is", async () => {
  const err = await _handle(
    response({ detail: "API base and key are required" }),
    "/settings/test-connection",
    "POST"
  ).catch((e) => e);

  assert.equal(err.message, "API base and key are required");
});

test("an unexpected body keeps the generic message", async () => {
  const err = await _handle(
    response({ detail: null }, 500),
    "/settings",
    "PUT"
  ).catch((e) => e);

  assert.equal(err.message, "PUT /settings failed: 500");
});
