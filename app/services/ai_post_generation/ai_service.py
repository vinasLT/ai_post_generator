from typing import Any

from app.rpc_client.gen.python.auction.v1.lot_pb2 import Lot


class Transformers:

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
    def transform_lot_for_ai(cls, lots: list[Lot]) -> str:
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




