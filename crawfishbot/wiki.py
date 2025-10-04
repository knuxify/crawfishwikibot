# SPDX-License-Identifier: MIT

import pywikibot
from dataclasses import dataclass
import dataclasses
from dateutil import parser
from pprint import pprint
from typing import Optional
import pytz
import pytumblr
import re

from . import config, logger

tumblr = pytumblr.TumblrRestClient(
    config["tumblr"]["consumer_key"],
    config["tumblr"]["consumer_secret"],
    config["tumblr"]["oauth_token"],
    config["tumblr"]["oauth_secret"],
)

# Australian Central
#TIMEZONE = pytz.timezone('Australia/Melbourne')
#timezone_delta = timedelta(hours=9, minutes=30)
#timezone_delta_summer = timedelta(hours=10, minutes=30)

# Australian Eastern
TIMEZONE = pytz.timezone('Australia/Sydney')
#timezone_delta = timedelta(hours=10)
#timezone_delta_summer = timedelta(hours=11)

# New Zealand
#TIMEZONE = pytz.timezone('Pacific/Auckland')

site = pywikibot.Site('en', 'crawfish')
site.login()

@dataclass
class Comic:
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

    # With due apologies for the messy code. This was adapted from the initial
    # scraper used to bootstrap the wiki, then modified to do a single post,
    # then modified again to auto-update the latest comic number, then
    # modified again to fit it into a function... it really needs cleanup.

    post_id = post_url.replace("https://", "").replace("http://", "").split("/")[2]

    posts_raw = tumblr.posts("crawfishcomic", id=post_id, npf=True)
    pprint(posts_raw)
    assert "posts" in posts_raw
    post = posts_raw["posts"][0]

    comics = []
    videos = []

    LP_NUM_REGEX = "<!--NUMBER GOES HERE-->(?P<num>[0-9]*)<!--NUMBER ENDS HERE-->"
    latestpost = pywikibot.Page(site, "Template:Latest post")

    try:
        number = int(re.search(LP_NUM_REGEX, latestpost.text).group("num")) + 1
    except AttributeError as e:
        raise ValueError("Failed to extract number from Template:Latest post") from e
    except ValueError as e:
        raise ValueError("Could not parse number as integer; probably because the latest post was a video. Manual intervention is needed.") from e

    video_count = 1
    prev_is_video = None

    date = None
    url = post.get("post_url")
    tags = post.get("tags", [])
    has_crawfishcomic = False
    not_comic = False
    for tag in tags.copy():
        if tag.lower() == "crawfishcomic":
            tags.remove(tag)
            has_crawfishcomic = True
        if tag.lower() == "deleting later":
            not_comic = True
    if not_comic or post.get("type") == "ask":
        logger.warn(f"not a comic post?/ask? ({post.get('summary')}, {post.get('post_url')}")

    if not has_crawfishcomic:
        logger.warn(f"no CrawfishComic tag ({post.get('summary')}, {post.get('post_url')}")

    for tag in tags.copy():
        if "20" in tag:
            try:
                date = parser.parse(tag).strftime("%Y-%m-%d")
            except:
                logger.warn(f"WARNING: could not parse date for comic {number} ({tag})!")
            else:
                tags.remove(tag)
                break
    if not date:
        logger.warn(f"could not get date for comic {number}!")

    post_date = parser.parse(post.get("date")).astimezone(TIMEZONE).strftime("%Y-%m-%d")
    if date and int(date.replace('-', '')) > int(post_date.replace('-', '')):
        logger.info(f"date > post_date, probably timezone shenanigans: {number}: {date} > {post_date} (exact date {post.get('date')})")

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
                        logger.warn("media is string???", media, block.get("type"), pprint(post))
                    if media.get("has_original_dimensions", False):
                        image = media.get("url")
                        break
        elif "text" in block:
            content.append(block["text"])

    if not image:
        logger.warn(f"could not find main media for {url}! getting first url")
        for block in post.get("content"):
            if "media" in block:
                image = block.get("media")[0]["url"]
                break

    caption = "\n".join(content).strip()
    title = post.get("summary").split('\n')[0].split('. ')[0].strip()
    if title.endswith('.'):
        title = title[:-1]
    if caption == title:
        caption = None


    if not image:
        raise ValueError(f"could not get image for comic {number}!")

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

    if is_video:
        videos.append(comic)
        comic.prev_is_comic = comics[-1].number
        comics[-1].next_is_video = video_count
        comic.number = number
        prev_is_video = video_count
        video_count += 1
    else:
        if prev_is_video is not None:
            comic.prev_is_video = prev_is_video
            videos[-1].next_is_comic = number
            prev_is_video = None
        comics.append(comic)
        number += 1

    for comic in comics + videos:
        if comic.is_video:
            page_title = f"Video {comic.number}: {comic.title}"
        else:
            page_title = f"{comic.number}: {comic.title}"
        page = """{{Stub}}
    {{comic"""
        params = dataclasses.asdict(comic)
        for k,v in params.copy().items():
            k = k.replace('_', ' ')
            if v is None:
                continue
            if isinstance(v, bool):
                v = str(v).lower()
            if k == "tags":
                if not v:
                    continue
                v = ','.join(v)
            page += f"\n|{k}={v}"

        page += """\n}}
    == Explanation ==

    {{missing explanation}}

    == Transcript ==

    {{missing transcript}}"""

        wikipage = pywikibot.Page(site, page_title)
        #wikipage.put(page, "Typo fix")
        wikipage.text = page
        wikipage.save("New page")

        redirect_wikipage = pywikibot.Page(site, page_title.split(':')[0])
        redirect_wikipage.put(f"#REDIRECT [[{page_title}]]", "Auto-generated redirect")

    # We deliberately reuse the variable from the loop.
    if comic.is_video:
        new_num = f"Video {comic.number}"
    else:
        new_num = str(comic.number)

    latestpost.text = re.sub(LP_NUM_REGEX, f"<!--NUMBER GOES HERE-->{new_num}<!--NUMBER ENDS HERE-->", latestpost.text)
    latestpost.save("Update latest post")

    return f"https://crawfish.dissonant.dev/wiki/{page_title.replace(' ', '_')}"
