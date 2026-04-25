from typing import Any

import pytz

from app.database.models import Post
from app.rpc_client.gen.python.auction.v1 import lot_pb2
from app.rpc_client.gen.python.auction.v1.lot_pb2 import Lot
from app.services.lang_chain_agent.post_locale_strings import (
    POST_PUBLISH_LOCALES_ORDER,
    PostPublishLocale,
    locale_strings,
)


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
    """Builds Telegram HTML captions; `serialize()` stays Lithuanian for previews."""

    POST_PUBLISH_LOCALES_ORDER: tuple[PostPublishLocale, ...] = POST_PUBLISH_LOCALES_ORDER

    def __init__(self, post: Post):
        self.post = post

    def get_images(self, amount: int = 5):
        images = self.post.images.split(',')
        return images[:amount]

    def generate_link(self):
        # e.g. https://vinas.lt/lot/51015956/copart
        return f"https://vinas.lt/lot/{self.post.lot_id}/{self.post.auction.value}"

    def serialize(self, for_image: bool = False) -> str:
        return self.serialize_locale("lt", for_image=for_image)

    def serialize_locale(self, locale: PostPublishLocale, for_image: bool = False) -> str:
        s = locale_strings(locale)
        local_time = None
        if self.post.auction_date:
            vilnius_tz = pytz.timezone('Europe/Vilnius')
            local_time = self.post.auction_date.astimezone(vilnius_tz)
            local_time = local_time.strftime('%d.%m.%Y %H:%M')

        reserve = f'{self.post.reserve_price:,}' if self.post.reserve_price else 'N/A'
        delivery = str(self.post.delivery_price)
        shipping = str(self.post.shipping_price)
        avg = str(self.post.average_sell_price) if self.post.average_sell_price else None

        link_block = (
            f'🔗 <a href="{self.generate_link()}">{s["open_link"]}</a>\n\n'
            if not for_image else ''
        )

        auction_line = (
            s["auction_starts"].format(local_time=local_time)
            if local_time
            else s["auction_starts_na"]
        )

        reserve_line = s["reserve"].replace("${reserve}", reserve)
        odometer_line = s["odometer"].format(odometer=self.post.odometer)
        local_t = s["local_transport"].replace("${delivery}", delivery)
        sea_t = s["sea_transport"].replace("${shipping}", shipping)
        if avg:
            avg_line = s["avg_price"].replace("${avg}", avg)
        else:
            avg_line = s["avg_price_na"]

        primary = self.post.primary_damage or 'N/A'

        parts = [
            link_block,
            s["contact"] + "\n",
            s["headline"] + "\n",
            f"🚗 <b>{self.post.title}</b>\n",
            odometer_line + "\n",
            reserve_line + "\n",
            s["seller"] + "\n",
            f'{s["vin"]} {self.post.vin}\n',
            f'{s["condition"]} {self.post.status}\n',
            f'{s["primary_damage"]} {primary}\n',
            s["documents"] + "\n",
            auction_line + "\n",
            s["shipping_header"] + "\n",
            local_t + "\n",
            sea_t + "\n",
            s["broker_fee"] + "\n",
            s["auction_fees_note"] + "\n",
            s["taxes_header"] + "\n",
            s["tax_customs"] + "\n",
            s["tax_vat"] + "\n",
            s["tax_port"] + "\n",
            s["urgency"] + "\n",
            avg_line + "\n",
            s["cta"] + "\n\n",
        ]
        text = "".join(parts)
        if self.post.comment:
            text += f'<b>{self.post.comment}</b>'
        return text

    def texts_by_language_for_publish(self) -> list[dict[str, str]]:
        return [
            {"lang": lang, "text": self.serialize_locale(lang, for_image=False)}
            for lang in POST_PUBLISH_LOCALES_ORDER
        ]
