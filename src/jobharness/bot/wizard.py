"""Resumable conversation engine (plan step 4.2).

A :class:`Wizard` is a graph of :class:`Step` objects. State (current step,
answers, history) is persisted in ``bot_state`` after every answer so a
restart resumes mid-way. ``/back``, ``/skip`` and ``/cancel`` work everywhere.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from jobharness.bot.core import BotCore, Ctx

Answers = dict[str, Any]
ACTIVE_KEY = "wizard:active"


@dataclass
class Step:
    key: str
    prompt: str | Callable[[Answers], str]
    parse: Callable[[str, Answers], Any] = lambda text, _a: text.strip()
    optional: bool = False
    default: Any = None
    #: store the parsed value; default ``answers[key] = value``
    save: Callable[[Answers, Any], None] | None = None
    #: next step key; ``None`` -> sequential order, "" -> finish
    next: Callable[[Answers], str | None] | None = None

    def text(self, answers: Answers) -> str:
        return self.prompt(answers) if callable(self.prompt) else self.prompt


@dataclass
class Wizard:
    name: str
    steps: list[Step]
    on_complete: Callable[[Ctx, Answers], Awaitable[None]]
    intro: str = ""
    _index: dict[str, int] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._index = {s.key: i for i, s in enumerate(self.steps)}

    def step(self, key: str) -> Step:
        return self.steps[self._index[key]]

    def following(self, step: Step, answers: Answers) -> str:
        """Key of the next step, or "" when finished."""
        if step.next is not None:
            nxt = step.next(answers)
            if nxt is not None:
                return nxt
        i = self._index[step.key] + 1
        return self.steps[i].key if i < len(self.steps) else ""


class WizardRunner:
    def __init__(self, core: BotCore) -> None:
        self.core = core
        self.wizards: dict[str, Wizard] = {}
        core.text_handler = self.handle_text
        for name in ("back", "skip", "cancel"):
            core.commands[name] = self._control(name)

    def register(self, wizard: Wizard) -> None:
        self.wizards[wizard.name] = wizard

    # ------------------------------------------------------------ control
    async def start(
        self, ctx: Ctx, name: str, answers: Answers | None = None, first: str | None = None
    ) -> None:
        wiz = self.wizards[name]
        step = wiz.step(first) if first else wiz.steps[0]
        state: dict[str, Any] = {
            "wizard": name, "step": step.key, "answers": dict(answers or {}), "history": [],
        }
        ctx.services.state.set(ACTIVE_KEY, state)
        if wiz.intro:
            await ctx.reply(wiz.intro)
        await self._ask(ctx, wiz, step, state["answers"])

    def active(self, ctx: Ctx) -> dict[str, Any] | None:
        state = ctx.services.state.get(ACTIVE_KEY)
        return state if isinstance(state, dict) else None

    async def _ask(self, ctx: Ctx, wiz: Wizard, step: Step, answers: Answers) -> None:
        hint = "  (/skip to leave empty)" if step.optional else ""
        await ctx.reply(step.text(answers) + hint)

    async def _finish(self, ctx: Ctx, wiz: Wizard, answers: Answers) -> None:
        ctx.services.state.delete(ACTIVE_KEY)
        await wiz.on_complete(ctx, answers)

    def _control(self, name: str) -> Callable[[Ctx, str], Awaitable[None]]:
        async def handler(ctx: Ctx, _args: str) -> None:
            state = self.active(ctx)
            if state is None:
                await ctx.reply("Nothing to do right now. Send /help.")
                return
            wiz = self.wizards[state["wizard"]]
            answers: Answers = state["answers"]
            step = wiz.step(state["step"])
            if name == "cancel":
                ctx.services.state.delete(ACTIVE_KEY)
                await ctx.reply("Cancelled. Nothing was saved from this conversation.")
            elif name == "back":
                if not state["history"]:
                    await ctx.reply("Already at the first question.")
                    return
                state["step"] = state["history"].pop()
                ctx.services.state.set(ACTIVE_KEY, state)
                await self._ask(ctx, wiz, wiz.step(state["step"]), answers)
            elif name == "skip":
                if not step.optional:
                    await ctx.reply("This question is required.")
                    return
                await self._advance(ctx, wiz, state, step, step.default)

        return handler

    # ------------------------------------------------------------ answers
    async def handle_text(self, ctx: Ctx, text: str) -> bool:
        state = self.active(ctx)
        if state is None:
            return False
        wiz = self.wizards[state["wizard"]]
        step = wiz.step(state["step"])
        try:
            value = step.parse(text, state["answers"])
        except ValueError as e:
            await ctx.reply(f"{e}\nTry again, or /back, /cancel.")
            return True
        await self._advance(ctx, wiz, state, step, value)
        return True

    async def _advance(
        self, ctx: Ctx, wiz: Wizard, state: dict[str, Any], step: Step, value: Any
    ) -> None:
        answers: Answers = state["answers"]
        if step.save is not None:
            step.save(answers, value)
        else:
            answers[step.key] = value
        nxt = wiz.following(step, answers)
        if not nxt:
            await self._finish(ctx, wiz, answers)
            return
        state["history"].append(step.key)
        state["step"] = nxt
        ctx.services.state.set(ACTIVE_KEY, state)
        await self._ask(ctx, wiz, wiz.step(nxt), answers)


def yes_no(text: str, _answers: Answers | None = None) -> bool:
    t = text.strip().lower()
    if t in {"y", "yes", "да", "д"}:
        return True
    if t in {"n", "no", "нет", "н"}:
        return False
    raise ValueError("Please answer yes or no.")


__all__ = ["ACTIVE_KEY", "Answers", "Step", "Wizard", "WizardRunner", "yes_no"]
