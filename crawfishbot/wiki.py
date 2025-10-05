# SPDX-License-Identifier: MIT
"""Code for interfacing with the wiki."""

import dataclasses
import re
from dataclasses import dataclass
from pprint import pprint
from typing import Optional

import pytumblr
import pytz
import pywikibot
from dateutil import parser

from . import config, logger

# CrawfishComic's timezone, Australian Eastern
TIMEZONE = pytz.timezone("Australia/Sydney")

tumblr = pytumblr.TumblrRestClient(
    config["tumblr"]["consumer_key"],
    config["tumblr"]["consumer_secret"],
    config["tumblr"]["oauth_token"],
    config["tumblr"]["oauth_secret"],
)

site = pywikibot.Site("en", "crawfish")
site.login()


@dataclass
class Comic:
    """Represents a comic or video posted by crawfishcomic."""

    number: int
    url: str
    title: str
    caption: Optional[str]
    image: str
    date: str
    post_date: str
    is_video: bool
    tags: list[str]

    prev_is_video: Optional[int] = None
    next_is_video: Optional[int] = None

    prev_is_comic: Optional[int] = None
    next_is_comic: Optional[int] = None


def make_wiki_page(post_url: str) -> str:
    """
    Make a wiki page for the comic with the given URL.

    Returns the URL of the resulting page.
    """

    # Get post ID from URL
    post_id = post_url.replace("https://", "").replace("http://", "").split("/")[2]

    # Get post from Tumblr API
    posts_raw = tumblr.posts("crawfishcomic", id=post_id, npf=True)
    assert "posts" in posts_raw
    post = posts_raw["posts"][0]
    url = post.get("post_url")

    # Get the number of the previous comic, based on Template:Latest post.
    LP_NUM_REGEX = "<!--NUMBER GOES HERE-->(?P<num>[0-9]*)<!--NUMBER ENDS HERE-->"
    latestpost = pywikibot.Page(site, "Template:Latest post")

    try:
        number = int(re.search(LP_NUM_REGEX, latestpost.text).group("num")) + 1
    except AttributeError as e:
        raise ValueError("Failed to extract number from Template:Latest post") from e
    except ValueError as e:
        raise ValueError(
            "Could not parse number as integer; probably because the latest post was a video. Manual intervention is needed."
        ) from e

    # Parse the post's tags'
    tags = post.get("tags", [])

    date = None
    has_crawfishcomic = False
    not_comic = False

    for tag in tags.copy():
        # All comics are tagged with #CrawfishComic and a date tag (e.g. September 25th 2025).
        if tag.lower() == "crawfishcomic":
            tags.remove(tag)
            has_crawfishcomic = True

        if "20" in tag:
            try:
                date = parser.parse(tag).strftime("%Y-%m-%d")
            except:  # noqa: E722
                logger.warn(
                    f"WARNING: could not parse date for comic {number} ({tag})!"
                )
            else:
                tags.remove(tag)
                break

        # Non-comic posts, typically ask responses, are *usually* tagged with #deleting later.
        if tag.lower() == "deleting later":
            not_comic = True

    if not_comic or post.get("type") == "ask":
        logger.warn(f"Not a comic post?/ask? ({post.get('summary')}, {url}")

    if not has_crawfishcomic:
        logger.warn(f"No CrawfishComic tag ({post.get('summary')}, {url}")

    if not date:
        logger.warn(f"Could not get date ({post.get('summary')}, {url}")

    # Compare the date from the tag to the actual date of the post.
    post_date = parser.parse(post.get("date")).astimezone(TIMEZONE).strftime("%Y-%m-%d")
    if date and int(date.replace("-", "")) > int(post_date.replace("-", "")):
        logger.warn(
            f"date > post_date, probably timezone shenanigans: {number}: {date} > {post_date} (exact date {post.get('date')})"
        )

    # Parse the contents of the post to get the comic.
    content = []
    image = None
    is_video = False
    for block in post.get("content"):
        if "media" in block:
            if block["type"] == "video":
                image = block.get("poster")[0]["url"]
                is_video = True
            else:
                for media in block.get("media"):
                    if isinstance(media, str):
                        logger.warn(
                            "media is string???", media, block.get("type"), pprint(post)
                        )
                    if media.get("has_original_dimensions", False):
                        image = media.get("url")
                        break
        elif "text" in block:
            content.append(block["text"])

    if not image:
        logger.warn(f"Could not find main media for {url}! Getting first URL.")
        for block in post.get("content"):
            if "media" in block:
                image = block.get("media")[0]["url"]
                break

    caption = "\n".join(content).strip()
    title = post.get("summary").split("\n")[0].split(". ")[0].strip()
    if title.endswith("."):
        title = title[:-1]
    if caption == title:
        caption = None

    if not image:
        raise ValueError(f"Could not get image for comic {number}!")

    elif image.endswith(".pnj"):
        image = image[:-1] + "g"

    comic = Comic(
        number=number,
        title=title,
        caption=caption,
        url=url,
        image=image,
        tags=tags,
        date=date,
        post_date=post_date,
        is_video=is_video,
    )

    # Create the wiki page
    if comic.is_video:
        number_str = f"Video {comic.number}"
    else:
        number_str = str(comic.number)

    page_title = f"{number_str}: {comic.title}"
    page = """{{Stub}}
{{comic"""

    ## Generate Template:Comic parameters from comic data
    params = dataclasses.asdict(comic)
    for k, v in params.copy().items():
        k = k.replace("_", " ")
        if v is None:
            continue
        if isinstance(v, bool):
            v = str(v).lower()
        if k == "tags":
            if not v:
                continue
            v = ",".join(v)
        page += f"\n|{k}={v}"

    page += """\n}}
== Explanation ==

{{missing explanation}}

== Transcript ==

{{missing transcript}}"""

    wikipage = pywikibot.Page(site, page_title)
    wikipage.text = page
    wikipage.save("New comic (bot edit)")

    # Create number redirect
    redirect_wikipage = pywikibot.Page(site, number_str)
    redirect_wikipage.put(f"#REDIRECT [[{page_title}]]", "Auto-generated redirect")

    # Update Template:LatestPost
    latestpost.text = re.sub(
        LP_NUM_REGEX,
        f"<!--NUMBER GOES HERE-->{number_str}<!--NUMBER ENDS HERE-->",
        latestpost.text,
    )
    latestpost.save("Update latest post (bot edit)")

    return f"https://crawfish.dissonant.dev/wiki/{page_title.replace(' ', '_')}"
