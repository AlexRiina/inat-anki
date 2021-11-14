"""
inaturalist scraper to anki scraper
"""

import logging
import argparse
import json
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import bs4
import requests

ANKI_HOST = "http://localhost:8765"


@dataclass
class Taxon:
    name: str
    scientific_name: str
    images: List[str]


def download_image(taxon, url, dest_dir) -> None:
    img_resp = requests.get(url)
    nice_taxon = taxon.replace(" ", "_").lower()
    ext = {
        "image/jpeg": "jpg",
    }[img_resp.headers["Content-Type"]]
    for i in range(10):
        try:
            with open(f"{dest_dir}/{nice_taxon}.{i}.{ext}", "xb") as img_file:
                img_file.write(img_resp.content)
        except FileExistsError:
            pass
        else:
            break


def download_taxon(url) -> Optional[Taxon]:
    resp = requests.get(url)
    soup = bs4.BeautifulSoup(resp.content, "html5lib")
    script = soup.find("script", text=re.compile(".*taxon:"))

    match = re.search("taxon: ({.*})", script.contents[0])
    if match:
        photos = json.loads(match.group(1))["results"][0]["taxon_photos"]
        name = photos[0]["taxon"]["preferred_common_name"]
        scientific_name = photos[0]["taxon"]["name"]
        images = [photo["photo"]["medium_url"] for photo in photos]
        return Taxon(name, scientific_name, images)


def download_species_list(url) -> Iterable[Taxon]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    resp = requests.get(
        "https://api.inaturalist.org/v1/observations/species_counts", params=query
    )
    resp.raise_for_status()
    for taxon_data in resp.json()["results"]:
        if int(taxon_data['count']) < 10:
            logging.info("Skipping %s", taxon_data['taxon']['name'])
            continue

        try:
            taxon = download_taxon(
                f"https://www.inaturalist.org/taxa/{taxon_data['taxon']['id']}",
            )
            if taxon:
                yield taxon
        except Exception:
            logging.warning("Unable to download %s", taxon_data['taxon']['name'])


def create_anki_card(taxon: Taxon):
    resp = requests.post(
        ANKI_HOST,
        json={
            "action": "addNote",
            "version": 6,
            "params": {
                "note": {
                    "deckName": "Default",
                    "modelName": "Inaturalist",
                    "fields": {
                        "Name": taxon.name,
                        "Scientific Name": taxon.scientific_name,
                    },
                    "options": {
                        "allowDuplicate": False,
                        "duplicateScope": "deck",
                        "duplicateScopeOptions": {
                            "deckName": "Default",
                            "checkChildren": False,
                            "checkAllModels": False,
                        },
                    },
                    "tags": ["inaturalist"],
                    "picture": [
                        {
                            "url": image,
                            "filename": f"{taxon.scientific_name}_{index}.jpg",
                            "fields": [f"Image {index}"],
                        }
                        for index, image in enumerate(taxon.images[:4], 1)
                    ],
                }
            },
        },
    )
    resp.raise_for_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+", description="taxa or search results page")
    args = parser.parse_args()

    for url in args.urls:
        if "/taxa" in url:
            taxon = download_taxon(url)
            if taxon:
                create_anki_card(taxon)
        elif "/observations" in url:
            for taxon in download_species_list(url):
                create_anki_card(taxon)
