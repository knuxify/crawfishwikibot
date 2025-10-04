# crawfishwiki bot

Bot made for automating some tasks related to the [crawfishcomic wiki](https://crawfish.dissonant.dev).

## Setup

This guide assumes you're using uv for dependency management.

* Get dependencies (e.g. with uv install)
* Run `uv run ./setup` to do the initial pywikibot setup
* Patch pywikibot to evaluate captcha questions
* Run `uv run ./run` to launch the bot
