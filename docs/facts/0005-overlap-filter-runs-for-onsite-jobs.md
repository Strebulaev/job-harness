---
id: "0005"
title: "Overlap filter also runs for onsite jobs"
status: active
date: 2026-10-08
tags: [routing]
kind: decision
governed-by: TBD
---

The overlap check is not skipped when `remote_policy == "onsite"` or `onsite_required`; both filters fire so every reason is recorded.
