"""
inaturalist scraper
"""

import argparse
import json
import re
from urllib.parse import parse_qs, urlparse

import bs4
import requests


def download_image(taxon, url, dest_dir) -> None:
    img_resp = requests.get(url)
    nice_taxon = taxon.replace(' ', '_').lower()
    ext = {
        'image/jpeg': 'jpg',
    }[img_resp.headers['Content-Type']]
    for i in range(10):
        try:
            with open(f'{dest_dir}/{nice_taxon}.{i}.{ext}', 'xb') as img_file:
                img_file.write(img_resp.content)
        except FileExistsError:
            pass
        else:
            break


def download_taxon(url, dest_dir):
    resp = requests.get(url)
    soup = bs4.BeautifulSoup(resp.content, "html5lib")
    script = soup.find("script", text=re.compile(".*taxon:"))

    match = re.search("taxon: ({.*})", script.contents[0])
    if match:
        creatures = json.loads(match.group(1))["results"][0]["taxon_photos"]
        for creature in creatures:
            print(creature['taxon']['preferred_common_name'])
            download_image(
                creature['taxon']['preferred_common_name'],
                creature['photo']['medium_url'],
                dest_dir,
            )


def download_species_list(url, dest_dir):
    # https://www.inaturalist.org/observations
    # {'place_id': 2, 'subview': 'map', taxon_id='118451', 'view': 'species'}

    # place_id=2&taxon_id=118451&locale=en-US
    # {'verifiable': 'true', 'spam': false, 'locale': "en-US", place_id: 2, taxon_id: 118451}

    parsed = urlparse(url) 
    query = parse_qs(parsed.query)

    resp = requests.get("https://api.inaturalist.org/v1/observations/species_counts", params=query)
    resp.raise_for_status()
    for taxon in resp.json()['results']:
        print(f"downloading {taxon['taxon']['preferred_common_name']}")
        download_taxon(f"https://www.inaturalist.org/taxa/{taxon['taxon']['id']}", dest_dir=dest_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls', nargs='+')
    parser.add_argument('--dest', required=True)
    args = parser.parse_args()

    for url in args.urls:
        if '/taxa' in url:
            download_taxon(url, args.dest)
        elif '/observations' in url:
            download_species_list(url, args.dest)
