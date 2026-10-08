---
id: provider-keys-never-persisted-in-clear
title: "Provider keys are deleted from chat at once and stored only encrypted"
status: active
date: 2026-10-08
tags: [safety, config]
governed-by: "0014"
grounded-in: ["facts/0014"]
derivation-note: >
  Given decision 0014 (keys are pasted in Telegram) and fact 0014 (bot chats
  are not end-to-end encrypted), the bot must delete the key message
  immediately and keep the key encrypted everywhere else.
go-getter:
  enforcement:
    - tier: 1
      check: A key-entry handler deletes the user's message before any other work, stores via the encrypted secret store, and never passes the key to logging or error replies
---

## Guardrail

A provider key pasted in chat MUST be deleted from the chat right after it is read, stored only through the encrypted secret store, and never written to logs, error messages, the repo or plaintext config. Replies confirm "connected" or "failed", never the key.
