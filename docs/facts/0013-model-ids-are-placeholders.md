---
id: "0013"
title: "config/config.yaml model ids are still placeholders"
status: active
date: 2026-10-08
tags: [llm, config]
kind: environmental
governed-by: "0013"
---

`llm.models.{parse,compose,judge,classify}` in `config/config.yaml` hold `<model-id-small>`, `<model-id-strong>` and `<model-id-strong-different-prompt-role>`. Decision 0008 and `DECISIONS.md` O2 call the choice signed off; no real ids are pinned. Live provider runs cannot work until they are.
