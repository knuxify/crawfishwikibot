# SPDX-License-Identifier: MIT
"""Helper bot for crawfishcomic wiki."""

import logging
import tomllib

logger = logging.Logger(__name__)

with open("config.toml", "rb") as config_file:
    config = tomllib.load(config_file)
