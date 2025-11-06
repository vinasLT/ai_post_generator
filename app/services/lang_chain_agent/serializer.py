from typing import Any

import pytz

from app.database.models import Post
from app.rpc_client.gen.python.auction.v1 import lot_pb2
from app.rpc_client.gen.python.auction.v1.lot_pb2 import Lot


class Serializer:

    @classmethod
    def generate_text_for_lot(cls, lot: Lot) -> str:
        return (f"#Lot ID: {lot.lot_id}\n"
                 f"Auction: {lot.base_site}\n"
                 f"Make: {lot.make}\n"
                 f"Model: {lot.model}\n"
                 f"Series: {lot.series}\n"
                 f"Damage primary: {lot.damage_pr}\n"
                 f"Damage secondary: {lot.damage_sec or 'N/A'}\n"
                 f"Year: {lot.year}\n"
                 f'Keys: {'Yes' if lot.keys else 'No'}\n'
                 f'Seller: {lot.seller if lot.seller else 'N/A'}\n'
                 f"Odometer(odometer status: {lot.odobrand}): {lot.odometer} miles\n"
                 f"Document: {lot.document}, Document old: {lot.document_old}\n"
                 f"Transmission: {lot.transmission}\n"
                 f"Status: {lot.status}\n"
                 f"Price reserve: {lot.price_reserve or 'N/A'}"
        )

    @classmethod
    def generate_text_for_pagination(cls, pagination: lot_pb2.Pagination) -> str:
        return (f'Page: {pagination.page} of {pagination.pages}\n'
                f'Page size: {pagination.size}\n'
                f'Available lots count: {pagination.count}')

    @classmethod
    def transform_lots_for_ai(cls, lots: list[Lot]) -> str:
        text = ''

        for idx, lot in enumerate(lots):
            text += f'{idx + 1}. ' + cls.generate_text_for_lot(lot) + '\n\n'
        return text

    @classmethod
    def transform_lot_for_ai_images(cls, lots: list[dict[Any, Any]]) -> str:
        text = ''
        for idx, lot in enumerate(lots):
            lot_obj = lot['lot']
            description = lot['description']
            score = lot['score']
            image_descrition_text = (f'INFO ABOUT LOT IMAGES:\n'
                                     f'Description: {description}\n'
                                     f'Images Score: {score}/10')

            text += f'{idx + 1}. ' + cls.generate_text_for_lot(lot_obj) + '\n' + image_descrition_text + '\n\n'
        return text

class SerializePost:
    def __init__(self, post: Post):
        self.post = post

    def get_images(self, amount: int = 5):
        images = self.post.images.split(',')
        return images[:amount]

    def generate_link(self):
        return f"https://bidauto.online/lot/{self.post.lot_id}?auction_name={self.post.auction.upper()}"

    def serialize(self, for_image: bool = False):
        local_time = None
        if self.post.auction_date:
            vilnius_tz = pytz.timezone('Europe/Vilnius')
            local_time = self.post.auction_date.astimezone(vilnius_tz)
            local_time = local_time.strftime('%d.%m.%Y %H:%M')
        text = (
            f"{f'🔗 <a href=\"{self.generate_link()}\">Atidaryti bidauto.online</a>\n\n' if not for_image else ''}"
            f"📲 Susisiekite: https://t.me/bidautoLT\n"
            f"🚗🔥 Labai geras pasiūlymas aukcione! 🔥🚗\n"
            f"🚗 <b>{self.post.title}</b>\n"
            f"🕔 <b>{self.post.odometer} miles</b>\n"
            f"⚠️ <u><b>REZERVAS: ${f'{self.post.reserve_price:,}' if self.post.reserve_price else 'N/A'}</b></u>\n"
            f"📌 Pardavėjas: Draudimas 👍\n"
            f"📌 VIN: {self.post.vin}\n"
            f"📌 Būklė: {self.post.status}\n"
            f"🔧 Pirminė žala: {self.post.primary_damage}\n"
            f"📌 Dokumentai: Tinka registracijai 👍\n"
            f"⏳ Aukcionas prasideda: {local_time if local_time else 'N/A'} (Vilnius)\n"
            f"🛳️ Transporto išlaidos sudarys:\n"
            f"Vietinis Transportas: ${self.post.delivery_price}\n"
            f"Jūrinis pervežimas: ${self.post.shipping_price}\n"
            f"Broker Fee: $299\n"
            f"*** Taip pat prisidės aukciono mokesčiai, kurie priklauso nuo statymo sumos!\n"
            f"🇱🇹 Lietuvoje liks sumokėti:\n"
            f"✅ 10% Muitas\n"
            f"✅ 21% PVM\n"
            f"✅ 350€ Krova\n"
            f"⏳ Liko mažai laiko – nepraleiskite progos! ⏳💨\n"
            f"💸 VIDUTINĖ pardavimo kaina: ${self.post.average_sell_price if self.post.average_sell_price else 'N/A'}\n"
            f"✉️ Rašykite mums DM arba apsilankykite 👉 bidauto.online\n\n"
            f"{f'<b>{self.post.comment}</b>' if self.post.comment else ''}"
        )
        return text


