---
id: superjob-api-shape-unverified
title: "SuperJob API v2 shape is assumed, not verified against official docs"
status: draft
date: 2026-10-08
tags: [ingest, compliance]
kind: environmental
governed-by: "0007"
expires: Principal confirms the shape and terms at the live smoke test (plan 6.3)
---

Assumed: `GET https://api.superjob.ru/2.0/vacancies/`, secret key in `X-Api-App-Id`, params `keyword`, `town`, `payment_from`, `count` (≤100), `page` (from 0); response `{objects, total, more}`; vacancy fields `id`, `profession`, `firm_name`, `vacancyRichText`, `payment_from/to`, `currency`, `link`, `date_published` (unix seconds). Rate limits and terms of use are unknown. Official docs were captcha-blocked on 2026-10-08.
