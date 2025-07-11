# maunium-stickerpicker - A fast and simple Matrix sticker picker widget.
# Copyright (C) 2020 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import Dict, Tuple
import argparse
import asyncio
import os.path
import json
from pathlib import Path
import re

from telethon import TelegramClient
from telethon.tl.functions.messages import GetAllStickersRequest, GetStickerSetRequest
from telethon.tl.types.messages import AllStickers
from telethon.tl.types import InputStickerSetShortName, Document, DocumentAttributeSticker
from telethon.tl.types.messages import StickerSet as StickerSetFull

from .lib import matrix, util


async def export_img(client: TelegramClient, document: Document) -> bytes:
    print(f"Downloading {document.id}")
    data = await client.download_media(document, file=bytes)
    data, width, height = util.convert_image(data)
    return data
    with open(f"{document.id}.png", "wb") as f:
        f.write(data)
        # w = png.Writer(size=(width, height), greyscale=False)
        # w.write(f, [int (x) for x in data])


def add_meta(document: Document, info: matrix.StickerInfo, pack: StickerSetFull) -> None:
    for attr in document.attributes:
        if isinstance(attr, DocumentAttributeSticker):
            info["body"] = attr.alt
    info["id"] = f"tg-{document.id}"
    info["net.maunium.telegram.sticker"] = {
        "pack": {
            "id": str(pack.set.id),
            "short_name": pack.set.short_name,
        },
        "id": str(document.id),
        "emoticons": [],
    }


async def reupload_pack(client: TelegramClient, pack: StickerSetFull, output_dir: str) -> None:
    out_dir = Path(f"out/{pack.set.short_name}")
    if out_dir.exists():
        print(f"Skipping {pack.set.short_name}")
        return
    out_dir.mkdir(exist_ok=True)

    print(f"downloading {pack.set.title} with {pack.set.count} stickers "
          f"and writing output to {out_dir}")

    img_datas: dict[int, bytes] = {}
    for document in pack.documents:
        img_datas[document.id] = await export_img(client, document)

    done = []
    for sticker in pack.packs:
        for document_id in sticker.documents:
            if document_id in img_datas:
                path = out_dir / Path(f"{sticker.emoticon}.png")

                # Deduplicate emojis
                idx = 0
                while path.exists():
                    idx += 1
                    path = out_dir / Path(f"{sticker.emoticon}_{idx}.png")

                img_hash = hash(img_datas[document_id])
                if img_hash not in done:
                    print(f"saving {sticker.emoticon} to {path}")
                    with open(path, "wb") as f:
                        _ = f.write(img_datas[document_id])
                    done.append(img_hash)


pack_url_regex = re.compile(r"^(?:(?:https?://)?(?:t|telegram)\.(?:me|dog)/addstickers/)?"
                            r"([A-Za-z0-9-_]+)"
                            r"(?:\.json)?$")

parser = argparse.ArgumentParser()

parser.add_argument("--list", help="List your saved sticker packs", action="store_true")
parser.add_argument("--session", help="Telethon session file name", default="sticker-import")
parser.add_argument("--config",
                    help="Path to JSON file with Matrix homeserver and access_token",
                    type=str, default="config.json")
parser.add_argument("--output-dir", help="Directory to write packs to", default="web/packs/",
                    type=str)
parser.add_argument("pack", help="Sticker pack URLs to import", action="append", nargs="*")


async def main(args: argparse.Namespace) -> None:
    await matrix.load_config(args.config)
    client = TelegramClient(args.session, 298751, "cb676d6bae20553c9996996a8f52b4d7")
    await client.start()

    if args.list:
        stickers: AllStickers = await client(GetAllStickersRequest(hash=0))
        index = 1
        width = len(str(len(stickers.sets)))
        print("Your saved sticker packs:")
        for saved_pack in stickers.sets:
            print(f"{index:>{width}}. {saved_pack.title} "
                  f"(t.me/addstickers/{saved_pack.short_name})")
            index += 1
    elif args.pack[0]:
        input_packs = []
        for pack_url in args.pack[0]:
            match = pack_url_regex.match(pack_url)
            if not match:
                print(f"'{pack_url}' doesn't look like a sticker pack URL")
                return
            input_packs.append(InputStickerSetShortName(short_name=match.group(1)))
        for input_pack in input_packs:
            pack: StickerSetFull = await client(GetStickerSetRequest(input_pack, hash=0))
            await reupload_pack(client, pack, args.output_dir)
    else:
        parser.print_help()

    await client.disconnect()


def cmd() -> None:
    asyncio.run(main(parser.parse_args()))


if __name__ == "__main__":
    cmd()
