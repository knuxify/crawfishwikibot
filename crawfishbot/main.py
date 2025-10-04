# SPDX-License-Identifier: MIT

import json
import time
import traceback
import os

import feedparser
import requests

from . import config, logger
from .wiki import make_wiki_page

HEADERS = {"User-Agent": "crawfishwiki bot (https://github.com/knuxify/crawfishwikibot"}


def load_state() -> dict:
    """Get bot state from state.json."""
    if os.path.exists("state.json"):
        try:
            with open("state.json") as state_file:
                return json.load(state_file)
        except json.decoder.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict):
    """Save bot state to state.json."""
    with open("state.json", "w+") as state_file:
        json.dump(state, state_file)


def post_to_webhook(webhook_url: str, content: str):
    """Post a message to the webhook."""
    r = requests.post(webhook_url, data={
        "content": content
    }, headers=HEADERS)
    if r.status_code != 204:
        logger.error(f"Failed to post to webhook: {r.status_code}")


def mainloop():
    webhook = config["discord_webhook_url"]
    retry_timeout = config.get("retry_timeout", 30)
    refresh_timeout = config.get("refresh_timeout", 600)

    state = load_state()
    if not state:
        state = {
            "last_post_id": 0
        }

    while True:
        # Fetch RSS feed for crawfishcomic on tumblr
        r = requests.get("https://crawfishcomic.tumblr.com/rss", headers=HEADERS)

        if r.status_code != 200:
            logger.error(f"Failed to get RSS feed: {r.status_code}; retrying in {retry_timeout} seconds.")
            time.sleep(retry_timeout)
            continue

        d = feedparser.parse(r.text)

        # If the latest post has a higher ID than the last checked post, then
        # there are new posts to parse.
        to_parse = []
        for entry in d.entries:
            entry_id = int(entry.guid.split("/")[-1])
            if entry_id <= state["last_post_id"]:
                break
            to_parse.insert(0, entry)

        for entry in to_parse:
            try:
                # Tumblr's RSS feed generator stores tags in "category" elements.
                tags = [t.term.lower() for t in entry.tags]
            except AttributeError:
                # Some posts have no tags.
                tags = []

            # Every comic has the tags "CrawfishComic" and a date tag.
            if "crawfishcomic" in tags:
                post_to_webhook(webhook, f"New comic from crawfishcomic: {entry.link.replace('tumblr.com', 'tpmblr.com')}")

                # Create a wiki page for the comic.
                try:
                    wiki_url = make_wiki_page(entry.link)
                except:  # noqa: E722 (we deliberately do not want to grind the entire bot to a halt)
                    logger.error("Failed to make wiki page for comic:")
                    traceback.print_exc()

                post_to_webhook(webhook, f"Comic on the crawfishcomic wiki: {wiki_url}")

            # Posts without the CrawfishComic tag are usually singular, simple posts.
            else:
                post_to_webhook(webhook, f"New post from crawfishcomic: {entry.link}")

        save_state(state)

        time.sleep(refresh_timeout)
