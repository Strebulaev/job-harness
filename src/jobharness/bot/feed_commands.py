"""RSS feed management (plan step 4.6). Feeds live in the settings overlay."""

from __future__ import annotations

from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from jobharness.bot.core import BotCore, Ctx
from jobharness.bot.user_settings import load_settings, save_user_settings
from jobharness.bot.wizard import Answers, Step, Wizard, WizardRunner, yes_no
from jobharness.ingest.rss import _parse_feed

META_KEY = "feeds:meta"


def current_feeds(ctx: Ctx) -> list[str]:
    settings = load_settings(ctx.services.config_path, ctx.services.data_dir)
    return list(settings.ingest.rss_feeds) if settings.ingest else []


async def probe_feed(ctx: Ctx, url: str) -> list[str]:
    """Fetch once; return up to 3 item titles. Raises ValueError with a reason."""
    ua = load_settings(ctx.services.config_path, ctx.services.data_dir)
    agent = ua.ingest.user_agent if ua.ingest else "jobharness/0.1"
    try:
        async with httpx.AsyncClient(timeout=20.0, transport=ctx.services.transport) as client:
            resp = await client.get(url, headers={"User-Agent": agent})
    except httpx.HTTPError as e:
        raise ValueError(f"could not fetch the feed ({type(e).__name__})") from None
    if resp.status_code != 200:
        raise ValueError(f"the feed returned HTTP {resp.status_code}")
    try:
        items = _parse_feed(resp.text)
    except ElementTree.ParseError:
        raise ValueError("that URL is not valid RSS/Atom XML") from None
    if not items:
        raise ValueError("the feed has no items")
    return [str(i["title"])[:80] for i in items[:3]]


def register_feeds(core: BotCore, runner: WizardRunner) -> None:
    async def save_feed(ctx: Ctx, a: Answers) -> None:
        if not a["confirm"]:
            await ctx.reply("Feed not saved.")
            return
        feeds = current_feeds(ctx)
        if a["url"] in feeds:
            await ctx.reply("That feed is already added.")
            return
        feeds.append(a["url"])
        try:
            save_user_settings(
                ctx.services.config_path, ctx.services.data_dir, {"ingest": {"rss_feeds": feeds}}
            )
        except ValueError as e:
            await ctx.reply(f"Not saved: {e}")
            return
        meta = ctx.services.state.get(META_KEY, {})
        meta[a["url"]] = {"name": a["name"], "tos_note": "user-attested"}
        ctx.services.state.set(META_KEY, meta)
        await ctx.reply(f"Feed added ({len(feeds)} total). Start the search with /run.")

    runner.register(Wizard("feed_confirm", [
        Step("confirm", "Save this feed? Only confirm if its terms allow automated reading. (yes/no)",
             yes_no),
    ], save_feed))

    @core.command("feeds", "list your RSS feeds")
    async def feeds(ctx: Ctx, _args: str) -> None:
        urls = current_feeds(ctx)
        meta = ctx.services.state.get(META_KEY, {})
        if not urls:
            await ctx.reply("No feeds yet. Add one: /feed_add <url> [name]")
            return
        await ctx.reply("Feeds:\n" + "\n".join(
            f"- {meta.get(u, {}).get('name') or u} ({u})" for u in urls
        ))

    @core.command("feed_add", "add an RSS feed: /feed_add <url> [name]")
    async def feed_add(ctx: Ctx, args: str) -> None:
        parts = args.split(maxsplit=1)
        if not parts:
            await ctx.reply("Usage: /feed_add <url> [name]")
            return
        url, name = parts[0], (parts[1] if len(parts) > 1 else parts[0])
        if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
            await ctx.reply("The URL must start with http:// or https://")
            return
        if url in current_feeds(ctx):
            await ctx.reply("That feed is already added.")
            return
        try:
            titles = await probe_feed(ctx, url)
        except ValueError as e:
            await ctx.reply(f"Not added: {e}.")
            return
        await ctx.reply("Feed looks valid. Sample items:\n- " + "\n- ".join(titles))
        await runner.start(ctx, "feed_confirm", {"url": url, "name": name})

    @core.command("feed_remove", "remove a feed: /feed_remove <url or name>")
    async def feed_remove(ctx: Ctx, args: str) -> None:
        target = args.strip()
        meta = ctx.services.state.get(META_KEY, {})
        urls = current_feeds(ctx)
        match = [u for u in urls if u == target or meta.get(u, {}).get("name") == target]
        if not match:
            await ctx.reply("No such feed. See /feeds.")
            return
        urls.remove(match[0])
        save_user_settings(ctx.services.config_path, ctx.services.data_dir, {"ingest": {"rss_feeds": urls}})
        meta.pop(match[0], None)
        ctx.services.state.set(META_KEY, meta)
        await ctx.reply("Feed removed.")


__all__ = ["current_feeds", "probe_feed", "register_feeds"]
