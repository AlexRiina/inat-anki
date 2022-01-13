"""
inaturalist scraper that to writes anki card via anki-connect
"""

import argparse
import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import bs4
import requests
import tqdm

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
        if int(taxon_data["count"]) < 10:
            logging.info("Skipping %s", taxon_data["taxon"]["name"])
            continue

        try:
            taxon = download_taxon(
                f"https://www.inaturalist.org/taxa/{taxon_data['taxon']['id']}",
            )
            if taxon:
                yield taxon
        except Exception:
            logging.warning("Unable to download %s", taxon_data["taxon"]["name"])


def create_anki_model(model_name):
    divider = '\n<hr id="answer">\n'

    resp = requests.post(
        ANKI_HOST,
        json={
            "action": "createModel",
            "version": 6,
            "params": {
                "modelName": "Inaturalist2",
                "inOrderFields": [
                    "Name",
                    "Scientific Name",
                    "Image 1",
                    "Image 2",
                    "Image 3",
                    "Image 4",
                ],
                "isCloze": False,
                "cardTemplates": [
                    {
                        "Name": "Name -> Scientific Name",
                        "Front": "{{Name}}",
                        "Back": "{{FrontSide}}" + divider + "{{Scientific Name}}",
                    },
                    {
                        "Name": "Image 1 -> Name",
                        "Front": "{{#Image 1}}<div style='font-family: \"Arial\"; font-size: 20px;'>{{Image 1}}</div>{{/Image 1}}",
                        "Back": "{{FrontSide}}" + divider + "{{Name}}",
                    },
                    {
                        "Name": "Image 2 -> Name",
                        "Front": "{{#Image 2}}<div style='font-family: \"Arial\"; font-size: 20px;'>{{Image 2}}</div>{{/Image 2}}",
                        "Back": "{{FrontSide}}" + divider + "{{Name}}",
                    },
                    {
                        "Name": "Image 3 -> Name",
                        "Front": "{{#Image 3}}<div style='font-family: \"Arial\"; font-size: 20px;'>{{Image 3}}</div>{{/Image 3}}",
                        "Back": "{{FrontSide}}" + divider + "{{Name}}",
                    },
                    {
                        "Name": "Image 4 -> Name",
                        "Front": "{{#Image 4}}<div style='font-family: \"Arial\"; font-size: 20px;'>{{Image 4}}</div>{{/Image 4}}",
                        "Back": "{{FrontSide}}" + divider + "{{Name}}",
                    },
                ],
            },
        },
    )

    resp.raise_for_status()
    if error := resp.json()["error"]:
        if "already exists" not in error:
            raise Exception(error)
        else:
            print("Inaturalist model already exists")


def create_anki_card(taxon: Taxon, anki_deck: str, anki_model: str, tags: List[str]):
    resp = requests.post(
        ANKI_HOST,
        json={
            "action": "addNote",
            "version": 6,
            "params": {
                "note": {
                    "deckName": anki_deck,
                    "modelName": anki_model,
                    "fields": {
                        "Name": taxon.name,
                        "Scientific Name": taxon.scientific_name,
                    },
                    "options": {
                        "allowDuplicate": False,
                        "duplicateScope": "deck",
                        "duplicateScopeOptions": {
                            "deckName": anki_deck,
                            "checkChildren": False,
                            "checkAllModels": False,
                        },
                    },
                    "tags": ["inaturalist", *tags],
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
    if error := resp.json()["error"]:
        if "duplicate" not in error:
            raise Exception(error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+", help="taxa or search results page")
    parser.add_argument("--anki-deck", required=True)
    parser.add_argument("--anki-model", default="Inaturalist")
    parser.add_argument("--anki-tags", nargs="+", default=[], help="anki tags")
    args = parser.parse_args()

    create_anki_model(args.anki_model)

    for url in tqdm.tqdm(args.urls, desc="url"):
        try:
            if "/taxa" in url:
                taxon = download_taxon(url)
                if taxon:
                    create_anki_card(taxon, args.anki_deck, args.anki_model, args.tags)
            elif "/observations" in url:
                for taxon in tqdm(download_species_list(url), desc="species"):
                    assert taxon  # tqdm seems to screw up type
                    create_anki_card(taxon, args.anki_deck, args.anki_model, args.tags)
        except Exception:
            logging.warning("unable to process %s", url, exc_info=True)
